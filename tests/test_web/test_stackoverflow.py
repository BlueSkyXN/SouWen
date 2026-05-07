"""StackOverflow（StackExchange）API 客户端单元测试。

覆盖 ``souwen.web.stackoverflow`` 中 StackOverflowClient 的字段映射、
HTML 标题解码、空结果处理、API Key 可选行为。

测试清单：
- ``test_search_basic``：基本搜索解析与字段映射
- ``test_init_without_api_key``：无 API Key 时正常初始化（不抛 ConfigError）
- ``test_html_unescape_title``：HTML 编码标题被正确解码
- ``test_search_empty_results``：空结果处理
- ``test_search_includes_api_key_when_present``：有 Key 时附带 key 参数
"""

from __future__ import annotations

import re

from pytest_httpx import HTTPXMock

from souwen.web.stackoverflow import StackOverflowClient


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

STACKOVERFLOW_RESPONSE = {
    "items": [
        {
            "question_id": 12345,
            "title": "How to use async &amp; await in Python?",
            "link": "https://stackoverflow.com/questions/12345/how-to-use-async-await",
            "score": 42,
            "answer_count": 5,
            "is_answered": True,
            "tags": ["python", "async-await", "asyncio"],
            "view_count": 9001,
            "creation_date": 1700000000,
            "last_activity_date": 1700100000,
            "accepted_answer_id": 67890,
        },
        {
            "question_id": 22222,
            "title": "What&#39;s the difference between list and tuple?",
            "link": "https://stackoverflow.com/questions/22222/list-vs-tuple",
            "score": 10,
            "answer_count": 2,
            "is_answered": False,
            "tags": ["python"],
            "view_count": 100,
            "creation_date": 1700200000,
        },
    ],
    "has_more": False,
    "quota_max": 300,
    "quota_remaining": 299,
}

EMPTY_RESPONSE = {
    "items": [],
    "has_more": False,
    "quota_remaining": 299,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_search_basic(httpx_mock: HTTPXMock):
    """search() 正确解析 JSON 并映射字段。"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.stackexchange\.com/2\.3/search/advanced.*"),
        json=STACKOVERFLOW_RESPONSE,
    )

    async with StackOverflowClient(api_key=None) as c:
        resp = await c.search("python async", max_results=10)

    assert resp.source == "stackoverflow"
    assert resp.query == "python async"
    assert resp.total_results == 2
    assert len(resp.results) == 2

    first = resp.results[0]
    assert first.source == "stackoverflow"
    assert first.engine == "stackoverflow"
    assert first.url == "https://stackoverflow.com/questions/12345/how-to-use-async-await"
    # raw 字段保留原始元数据
    assert first.raw["question_id"] == 12345
    assert first.raw["score"] == 42
    assert first.raw["answer_count"] == 5
    assert first.raw["tags"] == ["python", "async-await", "asyncio"]
    assert first.raw["is_answered"] is True
    # snippet 包含 tags / score / answers
    assert "python" in first.snippet
    assert "score=42" in first.snippet
    assert "answers=5" in first.snippet


async def test_init_without_api_key(monkeypatch):
    """无 API Key 时正常初始化，不抛 ConfigError。"""
    # 确保环境变量不会污染
    monkeypatch.delenv("SOUWEN_STACKOVERFLOW_API_KEY", raising=False)
    client = StackOverflowClient(api_key=None)
    assert client.api_key is None
    assert client.ENGINE_NAME == "stackoverflow"
    await client.close()


async def test_html_unescape_title(httpx_mock: HTTPXMock):
    """HTML 编码标题（&amp; / &#39;）被正确解码。"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.stackexchange\.com/2\.3/search/advanced.*"),
        json=STACKOVERFLOW_RESPONSE,
    )

    async with StackOverflowClient(api_key=None) as c:
        resp = await c.search("python")

    # &amp; → &
    assert resp.results[0].title == "How to use async & await in Python?"
    # &#39; → '
    assert resp.results[1].title == "What's the difference between list and tuple?"


async def test_search_empty_results(httpx_mock: HTTPXMock):
    """空 items 列表正常返回零结果。"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.stackexchange\.com/2\.3/search/advanced.*"),
        json=EMPTY_RESPONSE,
    )

    async with StackOverflowClient(api_key=None) as c:
        resp = await c.search("nothing-matches-xyz-123")

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == "stackoverflow"


async def test_search_includes_api_key_when_present(httpx_mock: HTTPXMock):
    """有 api_key 时请求 URL 中应包含 key 参数。"""
    httpx_mock.add_response(
        url=re.compile(r"https://api\.stackexchange\.com/2\.3/search/advanced.*"),
        json=EMPTY_RESPONSE,
    )

    async with StackOverflowClient(api_key="test-secret-key") as c:
        await c.search("python")

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    sent_url = str(requests[0].url)
    assert "key=test-secret-key" in sent_url
    assert "site=stackoverflow" in sent_url
    assert "sort=relevance" in sent_url
