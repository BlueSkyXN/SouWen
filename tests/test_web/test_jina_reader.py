"""Jina Reader 内容抓取客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.web.jina_reader`` 中 JinaReaderClient 的 JSON 解析、字段映射、
错误处理、批量并发等不变量。

测试清单：
- ``test_fetch_single_url``         ：正常抓取单个 URL
- ``test_fetch_with_api_key``       ：使用 API Key 设置 Authorization 头
- ``test_fetch_error_handling``     ：异常时返回 error 字段
- ``test_fetch_batch``              ：批量抓取多个 URL
- ``test_fetch_batch_partial``      ：批量中部分失败
- ``test_fetch_plain_text_fallback``：非 JSON 响应回退
"""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.web.jina_reader import JinaReaderClient


JINA_URL_RE = re.compile(r"https://r\.jina\.ai/.*")


def _make_jina_response(
    *,
    url: str = "https://example.com",
    title: str = "Example Page",
    content: str = "# Example\n\nThis is the content.",
    published_time: str | None = None,
    author: str | None = None,
) -> dict:
    """构造 Jina Reader JSON 响应。"""
    data: dict = {
        "url": url,
        "title": title,
        "content": content,
    }
    if published_time:
        data["publishedTime"] = published_time
    if author:
        data["author"] = author
    return {"code": 200, "status": 20000, "data": data}


@pytest.mark.asyncio
async def test_fetch_single_url(httpx_mock: HTTPXMock):
    """正常抓取返回 FetchResult，字段映射正确。"""
    httpx_mock.add_response(
        url=JINA_URL_RE,
        json=_make_jina_response(
            url="https://example.com/page",
            title="Test Page",
            content="# Hello\n\nWorld",
            published_time="2024-01-15",
            author="Author Name",
        ),
    )
    async with JinaReaderClient() as client:
        result = await client.fetch("https://example.com/page")

    assert result.error is None
    assert result.title == "Test Page"
    assert result.content == "# Hello\n\nWorld"
    assert result.content_format == "markdown"
    assert result.source == "jina_reader"
    assert result.final_url == "https://example.com/page"
    assert result.published_date == "2024-01-15"
    assert result.author == "Author Name"
    assert result.snippet.startswith("# Hello")


@pytest.mark.asyncio
async def test_fetch_with_api_key(httpx_mock: HTTPXMock):
    """API Key 正确设置 Authorization 头。"""
    httpx_mock.add_response(url=JINA_URL_RE, json=_make_jina_response())
    async with JinaReaderClient(api_key="test-key-123") as client:
        result = await client.fetch("https://example.com")

    assert result.error is None
    assert result.raw.get("has_key") is True
    # 验证请求头中包含 Bearer token
    req = httpx_mock.get_requests()[0]
    assert req.headers.get("authorization") == "Bearer test-key-123"


@pytest.mark.asyncio
async def test_fetch_error_handling(httpx_mock: HTTPXMock):
    """网络异常时返回 error 字段而非抛异常。"""
    httpx_mock.add_exception(Exception("Connection refused"))
    async with JinaReaderClient() as client:
        result = await client.fetch("https://example.com")

    assert result.error is not None
    assert "Connection refused" in result.error
    assert result.url == "https://example.com"
    assert result.source == "jina_reader"


@pytest.mark.asyncio
async def test_fetch_batch(httpx_mock: HTTPXMock):
    """批量抓取返回 FetchResponse，聚合计数正确。"""
    urls = ["https://a.com", "https://b.com", "https://c.com"]
    for url in urls:
        httpx_mock.add_response(
            url=JINA_URL_RE,
            json=_make_jina_response(url=url, title=f"Page {url}"),
        )
    async with JinaReaderClient() as client:
        resp = await client.fetch_batch(urls, max_concurrency=2)

    assert resp.total == 3
    assert resp.total_ok == 3
    assert resp.total_failed == 0
    assert resp.provider == "jina_reader"
    assert len(resp.results) == 3


@pytest.mark.asyncio
async def test_fetch_batch_partial(httpx_mock: HTTPXMock):
    """批量中部分失败，计数正确反映。"""
    httpx_mock.add_response(
        url=re.compile(r"https://r\.jina\.ai/https://ok\.com"),
        json=_make_jina_response(url="https://ok.com"),
    )
    httpx_mock.add_exception(
        Exception("Timeout"),
        url=re.compile(r"https://r\.jina\.ai/https://fail\.com"),
    )
    async with JinaReaderClient() as client:
        resp = await client.fetch_batch(["https://ok.com", "https://fail.com"])

    assert resp.total == 2
    assert resp.total_ok == 1
    assert resp.total_failed == 1
    ok_results = [r for r in resp.results if r.error is None]
    fail_results = [r for r in resp.results if r.error is not None]
    assert len(ok_results) == 1
    assert len(fail_results) == 1
