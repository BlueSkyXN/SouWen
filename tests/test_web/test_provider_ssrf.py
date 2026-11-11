"""Provider-level URL safety tests for direct fetch/content APIs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from souwen.providers.runtime_clients.models import FetchResult
from souwen.providers.runtime_clients.web.jina_reader import JinaReaderClient

BLOCKED_URL = "http://127.0.0.1/admin"
SAFE_URL = "https://1.1.1.1/page"


class _JsonResponse:
    def __init__(self, data: Any):
        self._data = data

    def json(self) -> Any:
        return self._data


async def _close_if_needed(client: object) -> None:
    close = getattr(client, "close", None)
    if close is not None:
        await close()


def _assert_blocked_result(result: FetchResult, provider: str) -> None:
    assert result.url == BLOCKED_URL
    assert result.final_url == BLOCKED_URL
    assert result.source == provider
    assert result.error is not None
    assert "SSRF" in result.error
    assert result.raw["blocked_by_ssrf"] is True


@pytest.mark.parametrize(
    ("provider", "factory", "call", "request_attr"),
    [
        ("jina_reader", JinaReaderClient, lambda client: client.fetch(BLOCKED_URL), "get"),
    ],
)
@pytest.mark.asyncio
async def test_direct_fetch_providers_block_ssrf_before_http(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    factory: Callable[[], object],
    call: Callable[[object], Awaitable[FetchResult]],
    request_attr: str,
) -> None:
    client = factory()
    request_mock = AsyncMock(side_effect=AssertionError("provider HTTP request should not run"))
    monkeypatch.setattr(client, request_attr, request_mock)

    try:
        result = await call(client)
    finally:
        await _close_if_needed(client)

    _assert_blocked_result(result, provider)
    request_mock.assert_not_awaited()
