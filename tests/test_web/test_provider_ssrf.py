"""Provider-level URL safety tests for direct fetch/content APIs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from souwen.providers.runtime_clients.models import FetchResult
from souwen.providers.runtime_clients.web.apify import ApifyClient
from souwen.providers.runtime_clients.web.cloudflare_browser import CloudflareBrowserClient
from souwen.providers.runtime_clients.web.diffbot import DiffbotClient
from souwen.providers.runtime_clients.web.exa import ExaClient
from souwen.providers.runtime_clients.web.firecrawl import FirecrawlClient
from souwen.providers.runtime_clients.web.jina_reader import JinaReaderClient
from souwen.providers.runtime_clients.web.metaso import MetasoClient
from souwen.providers.runtime_clients.web.scraperapi import ScraperAPIClient
from souwen.providers.runtime_clients.web.scrapfly import ScrapflyClient
from souwen.providers.runtime_clients.web.scrapingbee import ScrapingBeeClient
from souwen.providers.runtime_clients.web.tavily import TavilyClient
from souwen.providers.runtime_clients.web.xcrawl import XCrawlClient
from souwen.providers.runtime_clients.web.zenrows import ZenRowsClient

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
        (
            "scrapfly",
            lambda: ScrapflyClient(api_key="test-key"),
            lambda client: client.fetch(BLOCKED_URL),
            "get",
        ),
        (
            "scraperapi",
            lambda: ScraperAPIClient(api_key="test-key"),
            lambda client: client.fetch(BLOCKED_URL),
            "get",
        ),
        (
            "scrapingbee",
            lambda: ScrapingBeeClient(api_key="test-key"),
            lambda client: client.fetch(BLOCKED_URL),
            "get",
        ),
        (
            "diffbot",
            lambda: DiffbotClient(api_token="test-token"),
            lambda client: client.fetch(BLOCKED_URL),
            "get",
        ),
        (
            "zenrows",
            lambda: ZenRowsClient(api_key="test-key"),
            lambda client: client.fetch(BLOCKED_URL),
            "get",
        ),
        (
            "apify",
            lambda: ApifyClient(api_token="test-token"),
            lambda client: client.fetch(BLOCKED_URL),
            "post",
        ),
        (
            "cloudflare",
            lambda: CloudflareBrowserClient(api_token="test-token", account_id="acct"),
            lambda client: client.fetch(BLOCKED_URL),
            "post",
        ),
        (
            "firecrawl",
            lambda: FirecrawlClient(api_key="test-key"),
            lambda client: client.scrape(BLOCKED_URL),
            "post",
        ),
        (
            "xcrawl",
            lambda: XCrawlClient(api_key="test-key"),
            lambda client: client.scrape(BLOCKED_URL),
            "post",
        ),
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


@pytest.mark.asyncio
async def test_tavily_extract_filters_blocked_urls_before_batch_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TavilyClient(api_key="test-key")
    post = AsyncMock(
        return_value=_JsonResponse({"results": [{"url": SAFE_URL, "raw_content": "safe"}]})
    )
    monkeypatch.setattr(client, "post", post)

    try:
        response = await client.extract([SAFE_URL, BLOCKED_URL])
    finally:
        await client.close()

    post.assert_awaited_once()
    assert post.await_args.kwargs["json"]["urls"] == [SAFE_URL]
    assert response.total_ok == 1
    assert response.total_failed == 1
    assert [result.url for result in response.results] == [SAFE_URL, BLOCKED_URL]
    _assert_blocked_result(response.results[1], "tavily")


@pytest.mark.asyncio
async def test_exa_contents_filters_blocked_urls_before_batch_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ExaClient(api_key="test-key")
    post = AsyncMock(return_value=_JsonResponse({"results": [{"url": SAFE_URL, "text": "safe"}]}))
    monkeypatch.setattr(client, "post", post)

    try:
        response = await client.contents([SAFE_URL, BLOCKED_URL])
    finally:
        await client.close()

    post.assert_awaited_once()
    assert post.await_args.kwargs["json"]["urls"] == [SAFE_URL]
    assert response.total_ok == 1
    assert response.total_failed == 1
    assert [result.url for result in response.results] == [SAFE_URL, BLOCKED_URL]
    _assert_blocked_result(response.results[1], "exa")


@pytest.mark.asyncio
async def test_exa_find_similar_blocks_ssrf_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ExaClient(api_key="test-key")
    post = AsyncMock(side_effect=AssertionError("Exa findSimilar request should not run"))
    monkeypatch.setattr(client, "post", post)

    try:
        with pytest.raises(ValueError, match="SSRF"):
            await client.find_similar(BLOCKED_URL)
    finally:
        await client.close()

    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_apify_fetch_batch_filters_blocked_urls_before_actor_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ApifyClient(api_token="test-token")
    post = AsyncMock(
        return_value=_JsonResponse(
            [{"url": SAFE_URL, "markdown": "safe", "metadata": {"title": "safe"}}]
        )
    )
    monkeypatch.setattr(client, "post", post)

    try:
        response = await client.fetch_batch([SAFE_URL, BLOCKED_URL])
    finally:
        await client.close()

    post.assert_awaited_once()
    assert post.await_args.kwargs["json"]["startUrls"] == [{"url": SAFE_URL}]
    assert response.total_ok == 1
    assert response.total_failed == 1
    assert [result.url for result in response.results] == [SAFE_URL, BLOCKED_URL]
    _assert_blocked_result(response.results[1], "apify")


@pytest.mark.parametrize(
    ("method_name", "call"),
    [
        ("map", lambda client: client.map(BLOCKED_URL)),
        ("crawl", lambda client: client.crawl(BLOCKED_URL)),
    ],
)
@pytest.mark.asyncio
async def test_xcrawl_url_task_methods_block_ssrf_before_request(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    call: Callable[[XCrawlClient], Awaitable[dict[str, Any]]],
) -> None:
    client = XCrawlClient(api_key="test-key")
    post = AsyncMock(side_effect=AssertionError(f"XCrawl {method_name} request should not run"))
    monkeypatch.setattr(client, "post", post)

    try:
        with pytest.raises(ValueError, match="SSRF"):
            await call(client)
    finally:
        await client.close()

    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_metaso_reader_blocks_ssrf_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MetasoClient(api_key="test-key")
    post = AsyncMock(side_effect=AssertionError("Metaso reader request should not run"))
    monkeypatch.setattr(client, "post", post)

    try:
        response = await client.reader(BLOCKED_URL)
    finally:
        await client.close()

    post.assert_not_awaited()
    assert response.total == 1
    assert response.total_ok == 0
    assert response.total_failed == 1
    _assert_blocked_result(response.results[0], "metaso")
