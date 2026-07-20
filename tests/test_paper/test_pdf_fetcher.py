"""PDF fallback downloader security tests."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import httpx

from souwen.paper import pdf_fetcher


class _RecordingHttpxClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        follow_redirects: bool | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self.calls.append(
            {
                "url": url,
                "headers": headers or {},
                "follow_redirects": follow_redirects,
                "extensions": extensions,
            }
        )
        return self._responses.pop(0)


class _FakeSouWenClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._client = _RecordingHttpxClient(responses)


def _patch_dns(monkeypatch: Any, mapping: dict[str, str]) -> None:
    def fake_getaddrinfo(host: str, *_args: Any, **_kwargs: Any) -> list[Any]:
        if host not in mapping:
            raise socket.gaierror(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (mapping[host], 443))]

    monkeypatch.setattr(pdf_fetcher.socket, "getaddrinfo", fake_getaddrinfo)


async def test_download_pdf_binds_request_to_resolved_ip(monkeypatch: Any, tmp_path: Path) -> None:
    """PDF download must not let httpx re-resolve the original hostname."""
    _patch_dns(monkeypatch, {"safe.example": "93.184.216.34"})
    client = _FakeSouWenClient(
        [
            httpx.Response(
                200,
                content=b"%PDF-1.7\nbody",
                request=httpx.Request("GET", "https://93.184.216.34/paper.pdf"),
            )
        ]
    )

    result = await pdf_fetcher._download_pdf(
        "https://safe.example/paper.pdf",
        tmp_path / "paper.pdf",
        client,  # type: ignore[arg-type]
    )

    assert result == tmp_path / "paper.pdf"
    assert result.read_bytes().startswith(b"%PDF-")
    assert client._client.calls == [
        {
            "url": "https://93.184.216.34/paper.pdf",
            "headers": {"Host": "safe.example"},
            "follow_redirects": False,
            "extensions": {"sni_hostname": "safe.example"},
        }
    ]


async def test_download_pdf_rejects_redirect_target_resolving_to_private_ip(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """Redirect targets are resolved and blocked before the next request."""
    _patch_dns(
        monkeypatch,
        {
            "safe.example": "93.184.216.34",
            "private.example": "127.0.0.1",
        },
    )
    client = _FakeSouWenClient(
        [
            httpx.Response(
                302,
                headers={"location": "https://private.example/secret.pdf"},
                request=httpx.Request("GET", "https://93.184.216.34/paper.pdf"),
            )
        ]
    )

    result = await pdf_fetcher._download_pdf(
        "https://safe.example/paper.pdf",
        tmp_path / "paper.pdf",
        client,  # type: ignore[arg-type]
    )

    assert result is None
    assert len(client._client.calls) == 1
    assert client._client.calls[0]["url"] == "https://93.184.216.34/paper.pdf"
    assert not (tmp_path / "paper.pdf").exists()
