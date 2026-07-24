"""Common Runtime SSRF target resolver parity and dependency tests."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import socket
import threading
from typing import Any

import pytest

from souwen.common_runtime.security import (
    ResolvedFetchTarget,
    resolve_fetch_target,
    validate_fetch_url,
)
from souwen.common_runtime.security import fetch_target as canonical_fetch_target
from souwen.core.scraper import base as scraper_base
from souwen.web import fetch as legacy_fetch


def _addrinfo(address: str, port: int = 443) -> tuple[Any, ...]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))


def test_legacy_fetch_path_reexports_canonical_ssrf_interface() -> None:
    assert legacy_fetch.ResolvedFetchTarget is ResolvedFetchTarget
    assert legacy_fetch.resolve_fetch_target is resolve_fetch_target
    assert legacy_fetch.validate_fetch_url is validate_fetch_url


def test_base_scraper_uses_canonical_ssrf_interface() -> None:
    assert scraper_base.ResolvedFetchTarget is ResolvedFetchTarget
    assert scraper_base.resolve_fetch_target is resolve_fetch_target


def test_canonical_fetch_target_has_only_stdlib_dependencies() -> None:
    path = Path(canonical_fetch_target.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_roots = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        (node.module or "").split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert imported_roots == {"__future__", "dataclasses", "ipaddress", "socket", "urllib"}


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("ftp://example.com/file", "不允许的协议: ftp"),
        ("http://user:pass@example.com/", "URL 不允许包含用户信息"),
        ("http:///path", "缺少主机名"),
        ("http://example.com:invalid/", "端口号无效"),
        ("http://localhost./", "目标主机名为本地主机: localhost."),
        ("http://127.0.0.1/", "目标地址为内部/私有 IP: 127.0.0.1"),
        ("https://198.18.1.47/", "目标地址为内部/私有 IP: 198.18.1.47"),
        ("http://2130706433/", "非规范 IPv4 数字写法: 2130706433 (解析为 127.0.0.1)"),
    ],
)
def test_ssrf_rejection_reason_contract_is_preserved(url: str, reason: str) -> None:
    assert resolve_fetch_target(url) == (None, reason)
    assert validate_fetch_url(url) == (False, reason)


def test_resolver_preserves_synchronous_dns_and_ipv4_preference(monkeypatch) -> None:
    calls: list[tuple[int, str, int | None, int, int]] = []

    def getaddrinfo(
        host: str,
        port: int | None,
        family: int,
        socktype: int,
    ) -> list[tuple[Any, ...]]:
        calls.append((threading.get_ident(), host, port, family, socktype))
        return [
            _addrinfo("2606:4700:4700::1111"),
            _addrinfo("1.1.1.1"),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    target, reason = resolve_fetch_target("https://example.com:8443/path?q=1")

    assert inspect.iscoroutinefunction(resolve_fetch_target) is False
    assert list(inspect.signature(resolve_fetch_target).parameters) == ["url"]
    assert calls == [
        (
            threading.get_ident(),
            "example.com",
            None,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    ]
    assert reason == ""
    assert target == ResolvedFetchTarget(
        original_url="https://example.com:8443/path?q=1",
        connect_url="https://1.1.1.1:8443/path?q=1",
        host_header="example.com:8443",
        sni_hostname="example.com",
    )


def test_resolver_still_fails_closed_on_mixed_dns_answers(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            _addrinfo("1.1.1.1"),
            _addrinfo("169.254.169.254"),
        ],
    )

    assert resolve_fetch_target("https://example.com/resource") == (
        None,
        "目标地址为内部/私有 IP: 169.254.169.254",
    )


def test_legacy_validate_monkeypatch_still_controls_fetch_helpers(monkeypatch) -> None:
    monkeypatch.setattr(
        legacy_fetch,
        "validate_fetch_url",
        lambda _url: (False, "patched legacy guard"),
    )

    result = legacy_fetch.ssrf_blocked_fetch_result("https://example.com", "fixture")

    assert result is not None
    assert result.error == "SSRF 校验失败: patched legacy guard"
    assert result.raw == {"provider": "fixture", "blocked_by_ssrf": True}
