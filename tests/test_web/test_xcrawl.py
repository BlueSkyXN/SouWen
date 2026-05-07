"""XCrawl 客户端单元测试。"""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.web.xcrawl import XCrawlClient


XCRAWL_URL_RE = re.compile(r"https://run\.xcrawl\.com/.*")


def _scrape_response(url: str = "https://example.com") -> dict:
    return {
        "scrape_id": "scrape_123",
        "endpoint": "scrape",
        "version": "test-version",
        "status": "completed",
        "url": url,
        "data": {
            "markdown": "# Example\n\nContent",
            "metadata": {
                "title": "Example",
                "description": "Example description",
                "final_url": f"{url}/",
                "status_code": 200,
            },
            "credits_used": 1,
            "credits_detail": {"base_cost": 1},
        },
        "total_credits_used": 1,
    }


@pytest.mark.asyncio
async def test_search_maps_results_and_headers(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=XCRAWL_URL_RE,
        json={
            "search_id": "search_123",
            "endpoint": "search",
            "status": "completed",
            "query": "site:docs.xcrawl.com API",
            "data": {
                "status": "success",
                "credits_used": 2,
                "data": [
                    {
                        "title": None,
                        "url": "https://docs.xcrawl.com/",
                        "description": "XCrawl docs",
                        "position": 1,
                    }
                ],
            },
        },
    )

    async with XCrawlClient(api_key="test-xcrawl-key") as client:
        resp = await client.search(
            "site:docs.xcrawl.com API",
            max_results=2,
            location="US",
            language="en",
        )

    assert resp.source == "xcrawl"
    assert resp.total_results == 1
    assert resp.results[0].title == "https://docs.xcrawl.com/"
    assert resp.results[0].snippet == "XCrawl docs"
    assert resp.results[0].raw["position"] == 1

    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer test-xcrawl-key"
    assert request.url.path == "/v1/search"
    assert b'"limit":2' in request.content


@pytest.mark.asyncio
async def test_scrape_maps_markdown_result(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=XCRAWL_URL_RE, json=_scrape_response("https://example.com"))

    async with XCrawlClient(api_key="test-xcrawl-key") as client:
        result = await client.scrape("https://example.com")

    assert result.error is None
    assert result.source == "xcrawl"
    assert result.title == "Example"
    assert result.final_url == "https://example.com/"
    assert result.content == "# Example\n\nContent"
    assert result.content_format == "markdown"
    assert result.snippet == "Example description"
    assert result.raw["scrape_id"] == "scrape_123"

    request = httpx_mock.get_requests()[0]
    assert request.url.path == "/v1/scrape"
    assert b'"mode":"sync"' in request.content
    assert b'"formats":["markdown"]' in request.content


@pytest.mark.asyncio
async def test_scrape_batch_counts_partial_failures(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=XCRAWL_URL_RE, json=_scrape_response("https://ok.example"))
    httpx_mock.add_response(
        url=XCRAWL_URL_RE,
        json={
            "scrape_id": "scrape_failed",
            "endpoint": "scrape",
            "status": "failed",
            "url": "https://fail.example",
        },
    )

    async with XCrawlClient(api_key="test-xcrawl-key") as client:
        resp = await client.scrape_batch(["https://ok.example", "https://fail.example"])

    assert resp.provider == "xcrawl"
    assert resp.total == 2
    assert resp.total_ok == 1
    assert resp.total_failed == 1
    assert resp.results[1].error == "XCrawl scrape status=failed"


@pytest.mark.asyncio
async def test_map_and_crawl_raw_methods(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=XCRAWL_URL_RE,
        json={
            "map_id": "map_123",
            "endpoint": "map",
            "status": "completed",
            "data": {"links": ["https://example.com"], "total_links": 1},
        },
    )
    httpx_mock.add_response(
        url=XCRAWL_URL_RE,
        json={
            "crawl_id": "crawl_123",
            "endpoint": "crawl",
            "status": "crawling",
        },
    )
    httpx_mock.add_response(
        url=XCRAWL_URL_RE,
        json={
            "crawl_id": "crawl_123",
            "endpoint": "crawl",
            "status": "completed",
            "completed": 1,
            "total": 1,
            "data": [{"markdown": "# Page"}],
        },
    )

    async with XCrawlClient(api_key="test-xcrawl-key") as client:
        map_resp = await client.map("https://example.com", limit=5)
        crawl_resp = await client.crawl("https://example.com", limit=1, max_depth=1)
        crawl_result = await client.get_crawl_result("crawl_123")

    assert map_resp["data"]["links"] == ["https://example.com"]
    assert crawl_resp["crawl_id"] == "crawl_123"
    assert crawl_result["status"] == "completed"

    requests = httpx_mock.get_requests()
    assert requests[0].url.path == "/v1/map"
    assert requests[1].url.path == "/v1/crawl"
    assert requests[2].url.path == "/v1/crawl/crawl_123"
