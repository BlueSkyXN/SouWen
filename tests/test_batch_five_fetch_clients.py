from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from souwen.web import readability_fetcher
from souwen.web.readability_fetcher import ReadabilityFetcherClient


@pytest.mark.asyncio
async def test_readability_timeout_returns_a_stable_nonempty_error() -> None:
    client = object.__new__(ReadabilityFetcherClient)

    async def slow_fetch(*_args, **_kwargs):
        await asyncio.sleep(1)

    client._fetch_with_safe_redirects = slow_fetch
    result = await client.fetch("https://example.test/article", timeout=0.001)

    assert result.error == "抓取超时 (0.001s)"


@pytest.mark.asyncio
async def test_readability_rejects_oversized_html_before_parser(monkeypatch) -> None:
    client = object.__new__(ReadabilityFetcherClient)

    async def oversized_fetch(*_args, **_kwargs):
        return SimpleNamespace(
            text="x" * (readability_fetcher._MAX_PARSER_INPUT_CODE_POINTS + 1),
            status_code=200,
            extensions={"souwen_final_url": "https://example.test/article"},
        )

    parser = Mock()
    client._fetch_with_safe_redirects = oversized_fetch
    monkeypatch.setattr(readability_fetcher, "_extract_with_readability_sync", parser)
    result = await client.fetch("https://example.test/article", timeout=1)

    assert result.error == "页面内容超过解析上限"
    parser.assert_not_called()
