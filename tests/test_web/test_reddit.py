"""Reddit 公开 JSON API 客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.web.reddit`` 中 RedditClient 的 JSON 解析、字段映射、
permalink 拼接、selftext 截断、空结果处理及参数校验等不变量。

测试清单：
- ``test_search_basic_returns_results``：正常搜索返回归一化结果
- ``test_search_empty_results``：空结果处理（children=[]）
- ``test_search_truncates_long_selftext``：selftext 超长时截断为 300 字符
- ``test_search_permalink_prefix_concatenation``：permalink 自动拼接域名
- ``test_search_skips_incomplete_records``：缺 title / permalink 的记录被跳过
- ``test_search_respects_max_results``：max_results 上限生效
- ``test_search_invalid_sort_raises``：非法 sort 抛 ValueError
- ``test_search_invalid_time_filter_raises``：非法 time_filter 抛 ValueError
- ``test_search_user_agent_header_set``：自定义 User-Agent 正确设置
- ``test_search_collects_raw_metadata``：raw 字段收集元数据
"""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.models import SourceType
from souwen.web.reddit import RedditClient


# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------


def _make_post(
    *,
    title: str = "Test post",
    permalink: str = "/r/Python/comments/abc123/test_post/",
    selftext: str = "This is the body of the self post.",
    subreddit: str = "Python",
    score: int = 42,
    num_comments: int = 7,
    created_utc: float = 1_700_000_000.0,
    upvote_ratio: float = 0.95,
    is_self: bool = True,
    domain: str = "self.Python",
    author: str = "test_user",
    url: str | None = None,
) -> dict:
    """构造单条 Reddit child.data 字典。"""
    return {
        "data": {
            "title": title,
            "permalink": permalink,
            "selftext": selftext,
            "subreddit": subreddit,
            "score": score,
            "num_comments": num_comments,
            "created_utc": created_utc,
            "upvote_ratio": upvote_ratio,
            "is_self": is_self,
            "domain": domain,
            "author": author,
            "url": url or f"https://www.reddit.com{permalink}",
        }
    }


def _make_listing(posts: list[dict]) -> dict:
    """构造 Reddit Listing 响应外壳。"""
    return {
        "kind": "Listing",
        "data": {
            "after": None,
            "before": None,
            "children": posts,
            "dist": len(posts),
        },
    }


REDDIT_URL_RE = re.compile(r"https://www\.reddit\.com/search\.json")


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


async def test_search_basic_returns_results(httpx_mock: HTTPXMock):
    """search() 正常返回归一化结果，字段映射正确。"""
    payload = _make_listing(
        [
            _make_post(
                title="Asyncio is great",
                permalink="/r/Python/comments/aaa/asyncio_is_great/",
                selftext="Some body text",
                subreddit="Python",
                score=100,
            ),
            _make_post(
                title="FastAPI tutorial",
                permalink="/r/FastAPI/comments/bbb/fastapi_tutorial/",
                selftext="",
                subreddit="FastAPI",
                score=50,
                is_self=False,
                domain="github.com",
                url="https://github.com/example/fastapi-demo",
            ),
        ]
    )
    httpx_mock.add_response(url=REDDIT_URL_RE, json=payload)

    async with RedditClient() as c:
        resp = await c.search("python", max_results=10)

    assert resp.source == SourceType.WEB_REDDIT
    assert resp.query == "python"
    assert resp.total_results == 2
    assert len(resp.results) == 2

    first = resp.results[0]
    assert first.title == "Asyncio is great"
    assert first.url == (
        "https://www.reddit.com/r/Python/comments/aaa/asyncio_is_great/"
    )
    assert first.snippet == "Some body text"
    assert first.engine == "reddit"
    assert first.source == SourceType.WEB_REDDIT


async def test_search_empty_results(httpx_mock: HTTPXMock):
    """children 为空时返回空 results 列表，不报错。"""
    httpx_mock.add_response(url=REDDIT_URL_RE, json=_make_listing([]))

    async with RedditClient() as c:
        resp = await c.search("nonexistent_query_xyz_123")

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_REDDIT


async def test_search_truncates_long_selftext(httpx_mock: HTTPXMock):
    """selftext 超过 300 字符时被截断为 300 字符。"""
    long_text = "A" * 1000
    httpx_mock.add_response(
        url=REDDIT_URL_RE,
        json=_make_listing([_make_post(selftext=long_text)]),
    )

    async with RedditClient() as c:
        resp = await c.search("test")

    assert len(resp.results) == 1
    snippet = resp.results[0].snippet
    assert len(snippet) == RedditClient.SNIPPET_MAX_LEN == 300
    assert snippet == "A" * 300


async def test_search_permalink_prefix_concatenation(httpx_mock: HTTPXMock):
    """permalink 不含域名时自动拼接 https://www.reddit.com 前缀。"""
    permalink = "/r/MachineLearning/comments/xyz/cool_paper/"
    httpx_mock.add_response(
        url=REDDIT_URL_RE,
        json=_make_listing([_make_post(permalink=permalink)]),
    )

    async with RedditClient() as c:
        resp = await c.search("ml")

    assert resp.results[0].url == f"https://www.reddit.com{permalink}"
    # raw 中保留原始 permalink，便于上层使用
    assert resp.results[0].raw["permalink"] == permalink


async def test_search_skips_incomplete_records(httpx_mock: HTTPXMock):
    """缺 title 或 permalink 的记录被跳过，不影响其他记录。"""
    payload = _make_listing(
        [
            _make_post(title="", permalink="/r/x/comments/1/_/"),  # 空标题
            _make_post(title="No permalink", permalink=""),        # 空 permalink
            _make_post(title="Valid", permalink="/r/x/comments/2/v/"),
        ]
    )
    httpx_mock.add_response(url=REDDIT_URL_RE, json=payload)

    async with RedditClient() as c:
        resp = await c.search("test")

    assert len(resp.results) == 1
    assert resp.results[0].title == "Valid"


async def test_search_respects_max_results(httpx_mock: HTTPXMock):
    """API 多返回时仍按 max_results 截断。"""
    posts = [
        _make_post(title=f"Post {i}", permalink=f"/r/x/comments/{i}/p/")
        for i in range(20)
    ]
    httpx_mock.add_response(url=REDDIT_URL_RE, json=_make_listing(posts))

    async with RedditClient() as c:
        resp = await c.search("test", max_results=5)

    assert len(resp.results) == 5
    assert resp.results[0].title == "Post 0"
    assert resp.results[4].title == "Post 4"


async def test_search_invalid_sort_raises():
    """非法 sort 抛 ValueError。"""
    async with RedditClient() as c:
        with pytest.raises(ValueError, match="无效的 sort"):
            await c.search("q", sort="banana")


async def test_search_invalid_time_filter_raises():
    """非法 time_filter 抛 ValueError。"""
    async with RedditClient() as c:
        with pytest.raises(ValueError, match="无效的 time_filter"):
            await c.search("q", time_filter="forever")


async def test_search_user_agent_header_set(httpx_mock: HTTPXMock):
    """请求头携带自定义 User-Agent（避免 Reddit 限流）。"""
    httpx_mock.add_response(url=REDDIT_URL_RE, json=_make_listing([]))

    async with RedditClient() as c:
        await c.search("test")

    request = httpx_mock.get_request()
    ua = request.headers.get("User-Agent", "")
    assert "SouWen" in ua
    # 不应是默认 httpx UA
    assert "python-httpx" not in ua.lower()


async def test_search_collects_raw_metadata(httpx_mock: HTTPXMock):
    """raw 字段收集 subreddit / score / num_comments 等元数据。"""
    httpx_mock.add_response(
        url=REDDIT_URL_RE,
        json=_make_listing(
            [
                _make_post(
                    subreddit="rust",
                    score=999,
                    num_comments=42,
                    created_utc=1_700_000_000.5,
                    upvote_ratio=0.88,
                    is_self=False,
                    domain="github.com",
                    author="ferris",
                    url="https://github.com/rust-lang/rust",
                )
            ]
        ),
    )

    async with RedditClient() as c:
        resp = await c.search("rust")

    raw = resp.results[0].raw
    assert raw["subreddit"] == "rust"
    assert raw["score"] == 999
    assert raw["num_comments"] == 42
    assert raw["created_utc"] == 1_700_000_000.5
    assert raw["upvote_ratio"] == 0.88
    assert raw["is_self"] is False
    assert raw["domain"] == "github.com"
    assert raw["author"] == "ferris"
    # 非 self post 时 external_url 指向外链
    assert raw["external_url"] == "https://github.com/rust-lang/rust"
