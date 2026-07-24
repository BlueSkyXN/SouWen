"""Canonical OAuth transport identity, compatibility, and cancellation tests."""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import souwen.common_runtime.transport.oauth_client as canonical_module
from souwen.common_runtime.transport import HttpTransport, OAuthTransport
from souwen.core.exceptions import AuthError
from souwen.core.http_client import OAuthClient, SouWenHttpClient
from souwen.patent import cnipa, epo_ops


def _response(
    *,
    status_code: int = 200,
    payload: object = None,
    json_error: Exception | None = None,
) -> MagicMock:
    response = MagicMock(status_code=status_code)
    if json_error is not None:
        response.json.side_effect = json_error
    else:
        response.json.return_value = payload
    return response


def _client_double(*, post: AsyncMock | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        post=post or AsyncMock(),
        request=AsyncMock(),
        aclose=AsyncMock(),
    )


def _explicit_oauth_transport(client: object | None = None) -> OAuthTransport:
    with patch(
        "souwen.common_runtime.transport.http_client.httpx.AsyncClient",
        return_value=client or _client_double(),
    ):
        return OAuthTransport(
            base_url="https://api.example",
            headers={"X-Test": "value"},
            timeout=7,
            max_retries=3,
            proxy=None,
            follow_redirects=True,
            token_url="https://auth.example/oauth/token",
            client_id="client-id",
            client_secret="client-secret",
        )


def test_legacy_oauth_client_preserves_mro_and_uses_canonical_methods() -> None:
    assert issubclass(OAuthTransport, HttpTransport)
    assert issubclass(OAuthClient, OAuthTransport)
    assert issubclass(OAuthClient, SouWenHttpClient)
    assert OAuthClient.__mro__[:4] == (
        OAuthClient,
        OAuthTransport,
        SouWenHttpClient,
        HttpTransport,
    )
    assert OAuthClient._get_token_lock is OAuthTransport._get_token_lock
    assert OAuthClient._ensure_token is OAuthTransport._ensure_token
    assert OAuthClient.get is OAuthTransport.get
    assert OAuthClient.post is OAuthTransport.post
    assert epo_ops.OAuthClient is OAuthClient
    assert cnipa.OAuthClient is OAuthClient


def test_canonical_oauth_module_has_no_legacy_or_domain_dependencies() -> None:
    path = Path(canonical_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imported == {
        "__future__",
        "asyncio",
        "errors",
        "http_client",
        "httpx",
        "logging",
        "time",
        "typing",
    }
    source = path.read_text(encoding="utf-8")
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


def test_explicit_oauth_transport_constructs_without_config_resolution() -> None:
    with patch("souwen.common_runtime.transport.http_client.httpx.AsyncClient") as client_factory:
        client = OAuthTransport(
            base_url="https://api.example",
            headers={"X-Test": "value"},
            timeout=12.5,
            max_retries=9,
            proxy="http://proxy.example:8080",
            follow_redirects=False,
            token_url="https://auth.example/oauth/token",
            client_id="client-id",
            client_secret="client-secret",
        )

    options = client_factory.call_args.kwargs
    assert options["base_url"] == "https://api.example"
    assert options["headers"] == {"X-Test": "value"}
    assert options["timeout"].connect == 12.5
    assert options["proxy"] == "http://proxy.example:8080"
    assert options["follow_redirects"] is False
    assert client.max_retries == 9
    assert client.token_url == "https://auth.example/oauth/token"
    assert client.client_id == "client-id"
    assert client.client_secret == "client-secret"
    assert client._access_token is None
    assert client._token_expires_at == 0
    assert client._token_lock is None


def test_legacy_oauth_adapter_preserves_source_config_resolution() -> None:
    config = MagicMock(timeout=30, max_retries=3)
    config.resolve_base_url.return_value = "https://resolved.example"
    config.resolve_proxy.return_value = "http://source-proxy.example:8080"
    config.resolve_headers.return_value = {"X-Source": "source-value"}
    with (
        patch("souwen.core.http_client.get_config", return_value=config),
        patch("souwen.common_runtime.transport.http_client.httpx.AsyncClient") as client_factory,
    ):
        client = OAuthClient(
            base_url="https://default.example",
            token_url="https://auth.example/oauth/token",
            client_id="client-id",
            client_secret="client-secret",
            headers={"X-Caller": "caller-value"},
            timeout=8,
            source_name="oauth_source",
        )

    config.resolve_base_url.assert_called_once_with(
        "oauth_source", default="https://default.example"
    )
    config.resolve_proxy.assert_called_once_with("oauth_source")
    config.resolve_headers.assert_called_once_with("oauth_source")
    options = client_factory.call_args.kwargs
    assert options["base_url"] == "https://resolved.example"
    assert options["headers"]["X-Source"] == "source-value"
    assert options["headers"]["X-Caller"] == "caller-value"
    assert options["timeout"].connect == 8
    assert options["proxy"] == "http://source-proxy.example:8080"
    assert client.token_url == "https://auth.example/oauth/token"


def test_epo_and_cnipa_construct_with_canonical_oauth_operations() -> None:
    config = MagicMock(
        timeout=30,
        max_retries=3,
        epo_consumer_secret="epo-secret",
        cnipa_client_secret="cnipa-secret",
    )
    config.resolve_api_key.side_effect = lambda source, _field: {
        "epo_ops": "epo-client",
        "cnipa": "cnipa-client",
    }[source]
    config.resolve_base_url.side_effect = lambda _source, default: default
    config.resolve_proxy.return_value = None
    config.resolve_headers.return_value = {}
    with (
        patch("souwen.patent.epo_ops.get_config", return_value=config),
        patch("souwen.patent.cnipa.get_config", return_value=config),
        patch("souwen.core.http_client.get_config", return_value=config),
        patch("souwen.common_runtime.transport.http_client.httpx.AsyncClient"),
    ):
        epo = epo_ops.EpoOpsClient()
        chinese = cnipa.CnipaClient()

    assert isinstance(epo._http, OAuthTransport)
    assert isinstance(epo._http, SouWenHttpClient)
    assert isinstance(chinese._http, OAuthTransport)
    assert isinstance(chinese._http, SouWenHttpClient)
    assert epo._http._ensure_token.__func__ is OAuthTransport._ensure_token
    assert chinese._http._ensure_token.__func__ is OAuthTransport._ensure_token


@pytest.mark.asyncio
async def test_token_request_cancellation_releases_lock_and_preserves_empty_cache() -> None:
    started = asyncio.Event()

    async def blocking_post(*_args: object, **_kwargs: object) -> None:
        started.set()
        await asyncio.Event().wait()

    post = AsyncMock(side_effect=blocking_post)
    client = _explicit_oauth_transport(_client_double(post=post))
    task = asyncio.create_task(client._ensure_token())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not client._get_token_lock().locked()
    assert client._access_token is None
    assert client._token_expires_at == 0
    assert post.await_count == 1

    client._client.post = AsyncMock(
        return_value=_response(payload={"access_token": "recovered", "expires_in": 1200})
    )
    with patch("souwen.common_runtime.transport.oauth_client.time.monotonic", return_value=100):
        assert await client._ensure_token() == "recovered"
    assert client._access_token == "recovered"
    assert client._token_expires_at == 1300


@pytest.mark.asyncio
async def test_cancelled_lock_waiter_does_not_cancel_single_refresh() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocking_post(*_args: object, **_kwargs: object) -> MagicMock:
        started.set()
        await release.wait()
        return _response(payload={"access_token": "shared", "expires_in": 1200})

    post = AsyncMock(side_effect=blocking_post)
    client = _explicit_oauth_transport(_client_double(post=post))
    first = asyncio.create_task(client._ensure_token())
    await started.wait()
    waiter = asyncio.create_task(client._ensure_token())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    release.set()
    assert await first == "shared"
    assert post.await_count == 1
    assert not client._get_token_lock().locked()


@pytest.mark.asyncio
async def test_cache_boundary_and_default_expiry_are_preserved() -> None:
    post = AsyncMock(return_value=_response(payload={"access_token": "fresh"}))
    client = _explicit_oauth_transport(_client_double(post=post))
    client._access_token = "cached"
    client._token_expires_at = 200

    with patch("souwen.common_runtime.transport.oauth_client.time.monotonic", return_value=139):
        assert await client._ensure_token() == "cached"
    post.assert_not_awaited()

    with patch("souwen.common_runtime.transport.oauth_client.time.monotonic", return_value=140):
        assert await client._ensure_token() == "fresh"
    post.assert_awaited_once_with(
        "https://auth.example/oauth/token",
        data={"grant_type": "client_credentials"},
        auth=("client-id", "client-secret"),
    )
    assert client._token_expires_at == 1340


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_response(status_code=401), "OAuth token 获取失败: HTTP 401"),
        (_response(json_error=ValueError("bad json")), "OAuth token 响应解析失败"),
        (_response(payload={}), "OAuth 响应缺少 access_token"),
    ],
)
async def test_token_error_mapping_is_preserved(response: MagicMock, message: str) -> None:
    client = _explicit_oauth_transport(_client_double(post=AsyncMock(return_value=response)))
    with pytest.raises(AuthError, match=message):
        await client._ensure_token()
    assert client._access_token is None
    assert client._token_expires_at == 0


@pytest.mark.asyncio
async def test_bearer_injection_and_caller_header_precedence_are_preserved() -> None:
    response = MagicMock(status_code=200)
    transport = _client_double()
    transport.request.return_value = response
    client = _explicit_oauth_transport(transport)
    client._access_token = "cached-token"
    client._token_expires_at = 1000

    with patch("souwen.common_runtime.transport.oauth_client.time.monotonic", return_value=0):
        assert (
            await client.get(
                "/records",
                headers={"Authorization": "Caller override", "X-Request": "value"},
                retry_policy="single_attempt",
            )
            is response
        )

    transport.request.assert_awaited_once_with(
        "GET",
        "/records",
        params=None,
        headers={"Authorization": "Caller override", "X-Request": "value"},
    )
    transport.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_oauth_logs_do_not_include_credentials_or_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _explicit_oauth_transport(
        _client_double(
            post=AsyncMock(
                return_value=_response(
                    payload={"access_token": "returned-secret-token", "expires_in": 1200}
                )
            )
        )
    )
    with caplog.at_level(logging.DEBUG, logger="souwen.http"):
        assert await client._ensure_token() == "returned-secret-token"

    rendered = caplog.text
    assert "client-secret" not in rendered
    assert "client-id" not in rendered
    assert "returned-secret-token" not in rendered
