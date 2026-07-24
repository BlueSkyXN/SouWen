"""Explicit Common Runtime HTTP transport and legacy adapter conformance tests."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from tenacity import wait_none

from souwen.book.library_of_congress import LibraryOfCongressClient
from souwen.common_runtime.transport import (
    AuthError,
    HttpTransport,
    RateLimitError,
    SourceUnavailableError,
    SouWenError,
)
from souwen.core.http_client import DEFAULT_USER_AGENT, SouWenHttpClient
from souwen.research_output.datacite import DataCiteClient


def _explicit_transport(**overrides: object) -> HttpTransport:
    options: dict[str, object] = {
        "base_url": "https://provider.example",
        "headers": {"X-Test": "value"},
        "timeout": 7,
        "max_retries": 11,
        "proxy": None,
        "follow_redirects": True,
    }
    options.update(overrides)
    return HttpTransport(**options)  # type: ignore[arg-type]


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        timeout=30,
        max_retries=3,
        resolve_base_url=Mock(return_value="https://resolved.example"),
        resolve_proxy=Mock(return_value="http://source-proxy.example:8080"),
        resolve_headers=Mock(
            return_value={"User-Agent": "source-agent", "X-Source": "source-value"}
        ),
        resolve_backend=Mock(return_value="curl_cffi"),
        get_proxy=Mock(return_value="http://global-proxy.example:8080"),
    )


def test_explicit_transport_constructs_httpx_client_without_config_resolution() -> None:
    with patch("souwen.common_runtime.transport.http_client.httpx.AsyncClient") as client_factory:
        transport = _explicit_transport(
            base_url="https://api.example",
            headers={"Authorization": "test-value"},
            timeout=12.5,
            max_retries=9,
            proxy="http://proxy.example:8080",
            follow_redirects=False,
        )

    options = client_factory.call_args.kwargs
    assert transport.base_url == "https://api.example"
    assert transport.timeout == 12.5
    assert transport.max_retries == 9
    assert options["base_url"] == "https://api.example"
    assert options["headers"] == {"Authorization": "test-value"}
    assert options["timeout"].connect == 12.5
    assert options["proxy"] == "http://proxy.example:8080"
    assert options["follow_redirects"] is False
    assert options["limits"].max_connections == 100
    assert options["limits"].max_keepalive_connections == 20
    assert options["limits"].keepalive_expiry == 30.0


def test_legacy_adapter_preserves_source_resolution_and_header_precedence() -> None:
    config = _config()
    with (
        patch("souwen.core.http_client.get_config", return_value=config),
        patch("souwen.common_runtime.transport.http_client.httpx.AsyncClient") as client_factory,
    ):
        client = SouWenHttpClient(
            base_url="https://default.example",
            headers={"User-Agent": "caller-agent", "X-Caller": "caller-value"},
            timeout=8,
            max_retries=5,
            source_name="example_source",
        )

    config.resolve_base_url.assert_called_once_with(
        "example_source", default="https://default.example"
    )
    config.resolve_proxy.assert_called_once_with("example_source")
    config.resolve_headers.assert_called_once_with("example_source")
    config.resolve_backend.assert_not_called()
    config.get_proxy.assert_not_called()
    options = client_factory.call_args.kwargs
    assert isinstance(client, HttpTransport)
    assert options["base_url"] == "https://resolved.example"
    assert options["headers"] == {
        "User-Agent": "caller-agent",
        "X-Source": "source-value",
        "X-Caller": "caller-value",
    }
    assert options["timeout"].connect == 8
    assert options["proxy"] == "http://source-proxy.example:8080"
    assert options["follow_redirects"] is True
    assert client.max_retries == 5


def test_legacy_adapter_preserves_global_defaults_and_truthy_fallback() -> None:
    config = _config()
    with (
        patch("souwen.core.http_client.get_config", return_value=config),
        patch("souwen.common_runtime.transport.http_client.httpx.AsyncClient") as client_factory,
    ):
        client = SouWenHttpClient(timeout=0, max_retries=0)

    config.get_proxy.assert_called_once_with()
    config.resolve_base_url.assert_not_called()
    config.resolve_proxy.assert_not_called()
    config.resolve_headers.assert_not_called()
    options = client_factory.call_args.kwargs
    assert options["headers"] == {"User-Agent": DEFAULT_USER_AGENT}
    assert options["timeout"].connect == 30
    assert options["proxy"] == "http://global-proxy.example:8080"
    assert client.max_retries == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx.ConnectError("connect failed"), "连接失败"),
        (httpx.ReadTimeout("read timed out"), "请求超时"),
    ],
)
async def test_attempt_counts_and_network_error_mapping_are_preserved(
    error: Exception, message: str
) -> None:
    request = AsyncMock(side_effect=error)
    with patch(
        "souwen.common_runtime.transport.http_client.httpx.AsyncClient",
        return_value=SimpleNamespace(request=request),
    ):
        client = _explicit_transport()

    with pytest.raises(SourceUnavailableError, match=message):
        await client.get("/resource", retry_policy="single_attempt")
    assert request.await_count == 1

    request.reset_mock(side_effect=True)
    request.side_effect = error
    with (
        patch.object(HttpTransport._request_with_retry.retry, "wait", wait_none()),
        pytest.raises(SourceUnavailableError, match=message),
    ):
        await client.get("/resource")
    assert request.await_count == 3


@pytest.mark.asyncio
async def test_request_cancellation_is_not_wrapped_or_retried() -> None:
    request = AsyncMock(side_effect=asyncio.CancelledError())
    with patch(
        "souwen.common_runtime.transport.http_client.httpx.AsyncClient",
        return_value=SimpleNamespace(request=request),
    ):
        client = _explicit_transport()

    with pytest.raises(asyncio.CancelledError):
        await client.get("/cancelled")
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_retry_backoff_cancellation_is_not_wrapped_or_retried() -> None:
    request = AsyncMock(side_effect=httpx.ConnectError("connect failed"))

    def cancel_wait(_retry_state: object) -> None:
        raise asyncio.CancelledError

    with patch(
        "souwen.common_runtime.transport.http_client.httpx.AsyncClient",
        return_value=SimpleNamespace(request=request),
    ):
        client = _explicit_transport()

    with (
        patch.object(HttpTransport._request_with_retry.retry, "wait", cancel_wait),
        pytest.raises(asyncio.CancelledError),
    ):
        await client.get("/cancelled-backoff")
    assert request.await_count == 1


@pytest.mark.parametrize(
    ("status", "error_type", "message"),
    [
        (401, AuthError, "鉴权失败"),
        (403, AuthError, "权限不足"),
        (429, RateLimitError, "限流触发"),
        (500, SourceUnavailableError, r"数据源服务器错误 \(500\)"),
        (418, SouWenError, r"请求失败 \(418\)"),
    ],
)
def test_status_mapping_is_preserved(
    status: int, error_type: type[Exception], message: str
) -> None:
    response = httpx.Response(status, headers={"Retry-After": "2.5"})
    with pytest.raises(error_type, match=message) as caught:
        HttpTransport._check_response(response, "https://provider.example/resource")
    if status == 429:
        assert caught.value.retry_after == 2.5


def test_not_found_and_retry_after_parsing_are_preserved() -> None:
    HttpTransport._check_response(httpx.Response(404))
    assert HttpTransport._parse_retry_after("2.5") == 2.5
    assert HttpTransport._parse_retry_after("not-a-date") is None
    with patch("souwen.common_runtime.transport.http_client.time.time", return_value=0):
        assert HttpTransport._parse_retry_after("Thu, 01 Jan 1970 00:00:05 GMT") == 5.0


@pytest.mark.asyncio
async def test_subclass_status_hook_receives_url() -> None:
    response = httpx.Response(200)
    request = AsyncMock(return_value=response)
    seen: list[str | None] = []

    class CustomTransport(HttpTransport):
        @staticmethod
        def _check_response(resp: httpx.Response, url: str | None = None) -> None:
            assert resp is response
            seen.append(url)

    with patch(
        "souwen.common_runtime.transport.http_client.httpx.AsyncClient",
        return_value=SimpleNamespace(request=request),
    ):
        client = CustomTransport(
            base_url="https://provider.example",
            headers={},
            timeout=7,
            max_retries=3,
            proxy=None,
            follow_redirects=True,
        )

    assert await client.get("/hook", retry_policy="single_attempt") is response
    assert seen == ["/hook"]


@pytest.mark.asyncio
async def test_context_exit_delegates_close_for_normal_and_exception_paths() -> None:
    normal_client = SimpleNamespace(aclose=AsyncMock())
    failing_client = SimpleNamespace(aclose=AsyncMock())
    with patch(
        "souwen.common_runtime.transport.http_client.httpx.AsyncClient",
        side_effect=[normal_client, failing_client],
    ):
        normal = _explicit_transport()
        failing = _explicit_transport()

    async with normal as entered:
        assert entered is normal
    normal_client.aclose.assert_awaited_once_with()

    with pytest.raises(RuntimeError, match="context failure"):
        async with failing:
            raise RuntimeError("context failure")
    failing_client.aclose.assert_awaited_once_with()


def test_transport_has_no_stream_api_or_domain_dependencies() -> None:
    assert not hasattr(HttpTransport, "stream")
    module_path = Path("src/souwen/common_runtime/transport/http_client.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imports <= {
        "__future__",
        "email.utils",
        "errors",
        "httpx",
        "logging",
        "tenacity",
        "time",
        "typing",
    }
    source = module_path.read_text(encoding="utf-8")
    for forbidden in (
        "souwen.config",
        "souwen.core",
        "souwen.delivery",
        "souwen.modules",
        "souwen.providers",
        "souwen.registry",
        "souwen.server",
        "get_config",
        "source_name",
        "os.environ",
    ):
        assert forbidden not in source


def test_representative_provider_families_use_canonical_execution_core() -> None:
    config = _config()
    with (
        patch("souwen.core.http_client.get_config", return_value=config),
        patch("souwen.common_runtime.transport.http_client.httpx.AsyncClient"),
    ):
        datacite = DataCiteClient()
        library_of_congress = LibraryOfCongressClient()

    assert isinstance(datacite._client, HttpTransport)
    assert isinstance(library_of_congress._client, HttpTransport)
    assert SouWenHttpClient._request is HttpTransport._request
    assert SouWenHttpClient._request_once is HttpTransport._request_once
    assert SouWenHttpClient._request_with_retry is HttpTransport._request_with_retry
