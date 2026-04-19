"""Wikipedia MediaWiki Action API 客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.web.wikipedia`` 中 WikipediaClient 的 JSON 解析、字段映射、
URL 拼接、HTML 标签清理、空结果处理、多语言支持以及畸形响应处理等不变量。

测试清单：
- ``test_basic_search``         ：正常搜索返回归一化结果
- ``test_empty_results``        ：空结果（search=[]）处理
- ``test_html_cleanup``         ：snippet 中 MediaWiki 高亮标签被剥离
- ``test_max_results_param``    ：max_results 透传为 srlimit 并截断结果
- ``test_custom_language``      ：多语言子站点（en / ja）URL 正确
- ``test_parse_error``          ：畸形响应（缺字段 / 非 JSON / API error）
- ``test_user_agent_header_set``：自定义 User-Agent 正确设置
- ``test_url_encoding``         ：含空格 / 特殊字符的标题被正确 URL 编码
"""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.exceptions import ParseError
from souwen.models import SourceType
from souwen.web.wikipedia import WikipediaClient, _clean_html


# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------


def _make_item(
    *,
    title: str = "Python (programming language)",
    snippet: str = 'Python is a <span class="searchmatch">programming</span> language.',
    pageid: int = 23862,
    wordcount: int = 12345,
    size: int = 67890,
    timestamp: str = "2024-01-15T12:00:00Z",
    titlesnippet: str | None = None,
) -> dict:
    """构造单条 MediaWiki search 结果项。"""
    return {
        "ns": 0,
        "title": title,
        "pageid": pageid,
        "size": size,
        "wordcount": wordcount,
        "snippet": snippet,
        "titlesnippet": titlesnippet or title,
        "timestamp": timestamp,
    }


def _make_response(items: list[dict], total_hits: int | None = None) -> dict:
    """构造 MediaWiki action=query&list=search 响应外壳。"""
    return {
        "batchcomplete": "",
        "continue": {"sroffset": 10, "continue": "-||"},
        "query": {
            "searchinfo": {"totalhits": total_hits if total_hits is not None else len(items)},
            "search": items,
        },
    }


# 同时匹配 zh / en / ja / ... 子站点
WIKI_URL_RE = re.compile(r"https://[a-z\-]+\.wikipedia\.org/w/api\.php")


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------


async def test_basic_search(httpx_mock: HTTPXMock):
    """search() 正常返回归一化结果，字段映射正确。"""
    payload = _make_response(
        [
            _make_item(
                title="Asyncio",
                snippet='<span class="searchmatch">Asyncio</span> is a Python library.',
                pageid=111,
                wordcount=500,
                timestamp="2024-02-01T00:00:00Z",
            ),
            _make_item(
                title="FastAPI",
                snippet="A modern web framework.",
                pageid=222,
                wordcount=800,
            ),
        ]
    )
    httpx_mock.add_response(url=WIKI_URL_RE, json=payload)

    async with WikipediaClient(lang="zh") as c:
        resp = await c.search("python", max_results=10)

    assert resp.source == SourceType.WEB_WIKIPEDIA
    assert resp.query == "python"
    assert resp.total_results == 2
    assert len(resp.results) == 2

    first = resp.results[0]
    assert first.title == "Asyncio"
    assert first.url == "https://zh.wikipedia.org/wiki/Asyncio"
    assert first.snippet == "Asyncio is a Python library."
    assert first.engine == "wikipedia"
    assert first.source == SourceType.WEB_WIKIPEDIA
    assert first.raw["pageid"] == 111
    assert first.raw["wordcount"] == 500
    assert first.raw["timestamp"] == "2024-02-01T00:00:00Z"
    assert first.raw["lang"] == "zh"


async def test_empty_results(httpx_mock: HTTPXMock):
    """search 列表为空时返回空 results，不报错。"""
    httpx_mock.add_response(url=WIKI_URL_RE, json=_make_response([], total_hits=0))

    async with WikipediaClient() as c:
        resp = await c.search("zzzz_nonexistent_query_xyz")

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_WIKIPEDIA


async def test_html_cleanup(httpx_mock: HTTPXMock):
    """snippet 中 ``<span class="searchmatch">`` 等 HTML 标签被剥离，HTML 实体被解码。"""
    raw_snippet = (
        'AT&amp;T 与 <span class="searchmatch">人工智能</span> '
        "<b>研究</b>&nbsp;领域的&#x20;合作"
    )
    httpx_mock.add_response(
        url=WIKI_URL_RE,
        json=_make_response([_make_item(snippet=raw_snippet)]),
    )

    async with WikipediaClient() as c:
        resp = await c.search("ai")

    cleaned = resp.results[0].snippet
    assert "<span" not in cleaned
    assert "<b>" not in cleaned
    assert "&amp;" not in cleaned
    assert "&nbsp;" not in cleaned
    # 验证关键词与文字内容被保留
    assert "AT&T" in cleaned
    assert "人工智能" in cleaned
    assert "研究" in cleaned

    # 顺带覆盖 _clean_html 直接调用
    assert _clean_html("") == ""
    assert _clean_html("<i>hello</i>  world") == "hello world"


async def test_max_results_param(httpx_mock: HTTPXMock):
    """max_results 应作为 srlimit 透传，并对超额响应做截断。"""
    items = [
        _make_item(title=f"Page {i}", pageid=i, snippet=f"snippet {i}")
        for i in range(20)
    ]
    httpx_mock.add_response(url=WIKI_URL_RE, json=_make_response(items))

    async with WikipediaClient() as c:
        resp = await c.search("test", max_results=5)

    assert len(resp.results) == 5
    assert resp.results[0].title == "Page 0"
    assert resp.results[4].title == "Page 4"

    request = httpx_mock.get_request()
    # srlimit 应等于 max_results
    assert request.url.params["srlimit"] == "5"
    assert request.url.params["srsearch"] == "test"
    assert request.url.params["action"] == "query"
    assert request.url.params["list"] == "search"
    assert request.url.params["format"] == "json"


async def test_custom_language(httpx_mock: HTTPXMock):
    """多语言子站点：默认 lang 决定 base_url；search(lang=...) 单次覆盖。"""
    # 1) 实例默认 lang=en
    httpx_mock.add_response(
        url=re.compile(r"https://en\.wikipedia\.org/w/api\.php"),
        json=_make_response([_make_item(title="Quantum computing")]),
    )

    async with WikipediaClient(lang="en") as c:
        resp = await c.search("quantum")

    assert resp.results[0].url == "https://en.wikipedia.org/wiki/Quantum_computing"
    assert resp.results[0].raw["lang"] == "en"
    req1 = httpx_mock.get_requests()[-1]
    assert req1.url.host == "en.wikipedia.org"

    # 2) 实例默认 zh，单次调用覆盖为 ja
    httpx_mock.add_response(
        url=re.compile(r"https://ja\.wikipedia\.org/w/api\.php"),
        json=_make_response([_make_item(title="人工知能")]),
    )

    async with WikipediaClient(lang="zh") as c:
        resp = await c.search("AI", lang="ja")

    assert resp.results[0].url.startswith("https://ja.wikipedia.org/wiki/")
    assert resp.results[0].raw["lang"] == "ja"
    req2 = httpx_mock.get_requests()[-1]
    assert req2.url.host == "ja.wikipedia.org"


async def test_parse_error(httpx_mock: HTTPXMock):
    """畸形响应触发 ParseError：缺 query.search / API error / 非 JSON。"""
    # 1) 缺 query.search 字段
    httpx_mock.add_response(url=WIKI_URL_RE, json={"batchcomplete": ""})
    async with WikipediaClient() as c:
        with pytest.raises(ParseError, match="query.search"):
            await c.search("x")

    # 2) MediaWiki API 返回错误对象
    httpx_mock.add_response(
        url=WIKI_URL_RE,
        json={"error": {"code": "badvalue", "info": "Unrecognized value"}},
    )
    async with WikipediaClient() as c:
        with pytest.raises(ParseError, match="Wikipedia API 错误"):
            await c.search("x")

    # 3) 非 JSON 响应
    httpx_mock.add_response(
        url=WIKI_URL_RE,
        content=b"<html>not json</html>",
        headers={"Content-Type": "text/html"},
    )
    async with WikipediaClient() as c:
        with pytest.raises(ParseError, match="解析失败"):
            await c.search("x")


async def test_user_agent_header_set(httpx_mock: HTTPXMock):
    """请求头携带自定义 User-Agent（符合维基媒体 API 礼仪）。"""
    httpx_mock.add_response(url=WIKI_URL_RE, json=_make_response([]))

    async with WikipediaClient() as c:
        await c.search("test")

    request = httpx_mock.get_request()
    ua = request.headers.get("User-Agent", "")
    assert "SouWen" in ua
    assert "github.com/BlueSkyXN/SouWen" in ua
    # 不应是默认 httpx UA
    assert "python-httpx" not in ua.lower()


async def test_url_encoding(httpx_mock: HTTPXMock):
    """含空格 / 中文 / 特殊字符的标题被正确转义为维基条目 URL。"""
    httpx_mock.add_response(
        url=WIKI_URL_RE,
        json=_make_response(
            [
                _make_item(title="Machine learning"),
                _make_item(title="人工智能"),
                _make_item(title="C++"),
            ]
        ),
    )

    async with WikipediaClient(lang="zh") as c:
        resp = await c.search("topics")

    # 空格 → 下划线
    assert resp.results[0].url == "https://zh.wikipedia.org/wiki/Machine_learning"
    # 中文需 percent-encoding
    assert resp.results[1].url == "https://zh.wikipedia.org/wiki/%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD"
    # ``+`` 在 URL 路径中需转义为 %2B
    assert resp.results[2].url == "https://zh.wikipedia.org/wiki/C%2B%2B"
