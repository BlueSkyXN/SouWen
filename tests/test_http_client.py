"""Tests for the HTTP client's explicit retry policies without live requests."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from tenacity import wait_none

from souwen.core.exceptions import SourceUnavailableError
from souwen.core.http_client import OAuthClient, SouWenHttpClient


class _UrlAwareResponseClient(SouWenHttpClient):
    seen_url: str | None = None

    def _check_response(self, resp: httpx.Response, url: str) -> None:
        self.seen_url = url
        super()._check_response(resp, url)


@pytest.fixture
def http_config():
    config = MagicMock()
    config.get_proxy.return_value = None
    with patch("souwen.core.http_client.get_config", return_value=config):
        yield config


@pytest.mark.parametrize("error", [httpx.ConnectError("offline"), httpx.ReadTimeout("slow")])
async def test_single_attempt_network_errors_send_one_request(http_config, error):
    client = SouWenHttpClient(timeout=5)
    client._client.request = AsyncMock(side_effect=error)

    try:
        with pytest.raises(SourceUnavailableError):
            await client.get("https://private.example.test/search", retry_policy="single_attempt")
    finally:
        await client.close()

    assert client._client.request.await_count == 1


@pytest.mark.parametrize("error", [httpx.ConnectError("offline"), httpx.ReadTimeout("slow")])
async def test_default_policy_retries_network_errors_three_times(http_config, error):
    client = SouWenHttpClient(timeout=5)
    client._client.request = AsyncMock(side_effect=error)

    try:
        with patch.object(SouWenHttpClient._request_with_retry.retry, "wait", wait_none()):
            with pytest.raises(SourceUnavailableError):
                await client.get("https://private.example.test/search")
    finally:
        await client.close()

    assert client._client.request.await_count == 3


async def test_oauth_single_attempt_still_fetches_and_injects_token(http_config):
    client = OAuthClient(
        base_url="https://private.example.test",
        token_url="https://private.example.test/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
        timeout=5,
    )
    token_response = MagicMock(status_code=200)
    token_response.json.return_value = {"access_token": "token-value", "expires_in": 1200}
    response = MagicMock(status_code=200)
    client._client.post = AsyncMock(return_value=token_response)
    client._client.request = AsyncMock(return_value=response)

    try:
        await client.get("/records", retry_policy="single_attempt")
    finally:
        await client.close()

    client._client.post.assert_awaited_once()
    client._client.request.assert_awaited_once_with(
        "GET",
        "/records",
        params=None,
        headers={"Authorization": "Bearer token-value"},
    )


async def test_single_attempt_preserves_subclass_url_aware_response_hook(http_config):
    client = _UrlAwareResponseClient(timeout=5)
    response = MagicMock(status_code=200)
    client._client.request = AsyncMock(return_value=response)

    try:
        await client.get("/subclass-hook", retry_policy="single_attempt")
    finally:
        await client.close()

    assert client.seen_url == "/subclass-hook"


async def test_invalid_retry_policy_fails_before_sending(http_config):
    client = SouWenHttpClient(timeout=5)
    client._client.request = AsyncMock()

    try:
        with pytest.raises(ValueError, match="retry_policy"):
            await client.get("/records", retry_policy="invalid")  # type: ignore[arg-type]
    finally:
        await client.close()

    client._client.request.assert_not_awaited()


async def test_oauth_invalid_retry_policy_fails_before_token_request(http_config):
    client = OAuthClient(
        base_url="https://private.example.test",
        token_url="https://private.example.test/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
        timeout=5,
    )
    client._client.post = AsyncMock()
    client._client.request = AsyncMock()

    try:
        with pytest.raises(ValueError, match="retry_policy"):
            await client.get("/records", retry_policy="invalid")  # type: ignore[arg-type]
    finally:
        await client.close()

    client._client.post.assert_not_awaited()
    client._client.request.assert_not_awaited()
