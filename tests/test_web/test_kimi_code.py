"""Kimi Code 搜索与网页获取客户端测试。"""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from souwen.core.exceptions import ConfigError, ParseError
from souwen.web.kimi_code import KimiCodeClient


async def test_init_without_api_key_raises(monkeypatch):
    monkeypatch.delenv("SOUWEN_KIMI_CODE_API_KEY", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        KimiCodeClient()
    assert "kimi_code_api_key" in str(exc_info.value)


async def test_search_maps_results_and_headers(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.kimi.com/coding/v1/search",
        json={
            "search_results": [
                {
                    "site_name": "Example",
                    "title": "Example Title",
                    "url": "https://example.com/article",
                    "snippet": "Example summary",
                    "content": "Full content",
                    "date": "2026-05-16",
                    "icon": "https://example.com/favicon.ico",
                    "mime": "text/html",
                }
            ]
        },
    )

    async with KimiCodeClient(api_key="kimi-test-key") as client:
        resp = await client.search("SouWen Kimi", max_results=99, include_content=True)

    assert resp.source == "kimi_code"
    assert resp.total_results == 1
    first = resp.results[0]
    assert first.source == "kimi_code"
    assert first.engine == "kimi_code"
    assert first.title == "Example Title"
    assert first.url == "https://example.com/article"
    assert first.snippet == "Example summary"
    assert first.raw["site_name"] == "Example"
    assert first.raw["content"] == "Full content"

    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer kimi-test-key"
    assert request.headers["x-msh-platform"] == "kimi_cli"
    assert request.headers["content-type"] == "application/json"
    payload = json.loads(request.content)
    assert payload == {
        "text_query": "SouWen Kimi",
        "limit": 20,
        "enable_page_crawling": True,
        "timeout_seconds": 30,
    }


async def test_search_invalid_json_raises_parse_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.kimi.com/coding/v1/search",
        text="not json",
        headers={"Content-Type": "application/json"},
    )

    async with KimiCodeClient(api_key="kimi-test-key") as client:
        with pytest.raises(ParseError, match="Kimi Code 搜索响应解析失败"):
            await client.search("bad response")


async def test_search_missing_results_raises_parse_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="https://api.kimi.com/coding/v1/search", json={"data": []})

    async with KimiCodeClient(api_key="kimi-test-key") as client:
        with pytest.raises(ParseError, match="search_results"):
            await client.search("bad schema")


async def test_fetch_returns_markdown_and_supports_pagination(httpx_mock: HTTPXMock, monkeypatch):
    monkeypatch.setattr("souwen.web.fetch.validate_fetch_url", lambda url: (True, ""))
    httpx_mock.add_response(
        url="https://api.kimi.com/coding/v1/fetch",
        text="# Title\n\n0123456789abcdef",
        headers={"Content-Type": "text/markdown"},
    )

    async with KimiCodeClient(api_key="kimi-test-key") as client:
        result = await client.fetch("https://example.com/article", start_index=9, max_length=4)

    assert result.error is None
    assert result.source == "kimi_code"
    assert result.content == "0123"
    assert result.content_format == "markdown"
    assert result.content_truncated is True
    assert result.next_start_index == 13
    assert result.raw["provider"] == "kimi_code_fetch"

    request = httpx_mock.get_requests()[0]
    assert request.headers["accept"] == "text/markdown"
    assert request.headers["authorization"] == "Bearer kimi-test-key"
    assert json.loads(request.content) == {"url": "https://example.com/article"}


async def test_fetch_blocks_invalid_url_without_calling_api(httpx_mock: HTTPXMock):
    async with KimiCodeClient(api_key="kimi-test-key") as client:
        result = await client.fetch("http://127.0.0.1/admin")

    assert result.error is not None
    assert "SSRF" in result.error
    assert result.source == "kimi_code"
    assert result.raw["provider"] == "kimi_code_fetch"
    assert result.raw["blocked_by_ssrf"] is True
    assert not httpx_mock.get_requests()


async def test_fetch_batch_counts_partial_failures(httpx_mock: HTTPXMock, monkeypatch):
    monkeypatch.setattr(
        "souwen.web.fetch.validate_fetch_url",
        lambda url: (False, "blocked") if "blocked" in url else (True, ""),
    )
    httpx_mock.add_response(
        url="https://api.kimi.com/coding/v1/fetch",
        text="ok content",
        headers={"Content-Type": "text/markdown"},
    )

    async with KimiCodeClient(api_key="kimi-test-key") as client:
        resp = await client.fetch_batch(
            ["https://example.com/ok", "https://blocked.example/private"],
            max_concurrency=1,
        )

    assert resp.provider == "kimi_code"
    assert resp.total == 2
    assert resp.total_ok == 1
    assert resp.total_failed == 1
    assert resp.results[0].content == "ok content"
    assert resp.results[1].error == "SSRF 校验失败: blocked"
