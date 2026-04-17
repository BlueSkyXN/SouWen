"""Web 聚合搜索单元测试。

覆盖 ``souwen.web.search`` 中 web_search() 聚合函数与 _deduplicate() 去重逻辑。
Mock 各引擎的 search 方法而非 HTTP 请求本身（因为 scraper 引擎走 HTML 解析路径较复杂）。

验证 URL 去重（大小写不敏感、斜杠规范化）、搜索聚合、多引擎容错等不变量。

测试清单：
- ``test_deduplicate_removes_duplicates``：去重保留首次出现
- ``test_deduplicate_case_insensitive``：URL 大小写不敏感
- ``test_deduplicate_empty``：空列表处理
- ``test_web_search_single_engine``：单引擎搜索
- ``test_web_search_multiple_engines_aggregates``：多引擎聚合
- ``test_web_search_duplicate_across_engines``：跨引擎去重
- ``test_web_search_respects_num_results``：结果数限制
- ``test_web_search_engine_error_skipped``：错误引擎被跳过
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch


from souwen.models import WebSearchResult, SearchResponse, SourceType
from souwen.web.search import web_search, _deduplicate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(engine: str, title: str, url: str) -> WebSearchResult:
    """构造 WebSearchResult"""
    source_map = {
        "duckduckgo": SourceType.WEB_DUCKDUCKGO,
        "bing": SourceType.WEB_BING,
    }
    return WebSearchResult(
        source=source_map.get(engine, SourceType.WEB_DUCKDUCKGO),
        title=title,
        url=url,
        snippet=f"Snippet for {title}",
        engine=engine,
    )


def _make_engine_response(engine: str, results: list[WebSearchResult]) -> SearchResponse:
    """构造 SearchResponse"""
    source_map = {
        "duckduckgo": SourceType.WEB_DUCKDUCKGO,
        "bing": SourceType.WEB_BING,
    }
    return SearchResponse(
        query="test",
        source=source_map.get(engine, SourceType.WEB_DUCKDUCKGO),
        results=results,
        total_results=len(results),
    )


# ---------------------------------------------------------------------------
# _deduplicate tests
# ---------------------------------------------------------------------------


def test_deduplicate_removes_duplicates():
    """URL 去重保留首次出现"""
    results = [
        _make_result("duckduckgo", "Result 1", "https://example.com/page"),
        _make_result("bing", "Result 1 Dup", "https://example.com/page/"),
        _make_result("duckduckgo", "Result 2", "https://other.com"),
    ]
    deduped = _deduplicate(results)
    assert len(deduped) == 2
    assert deduped[0].engine == "duckduckgo"
    assert deduped[1].url == "https://other.com"


def test_deduplicate_case_insensitive():
    """URL 去重大小写不敏感"""
    results = [
        _make_result("duckduckgo", "A", "https://Example.COM/Page"),
        _make_result("bing", "B", "https://example.com/page"),
    ]
    deduped = _deduplicate(results)
    assert len(deduped) == 1


def test_deduplicate_empty():
    """空列表不崩溃"""
    assert _deduplicate([]) == []


# ---------------------------------------------------------------------------
# web_search aggregation tests
# ---------------------------------------------------------------------------


async def test_web_search_aggregates_engines():
    """web_search 正确聚合多引擎结果"""
    ddg_results = [_make_result("duckduckgo", "DDG 1", "https://ddg1.com")]
    bing_results = [_make_result("bing", "Bing 1", "https://bing1.com")]

    ddg_resp = _make_engine_response("duckduckgo", ddg_results)
    bing_resp = _make_engine_response("bing", bing_results)

    with (
        patch("souwen.web.search.DuckDuckGoClient") as mock_ddg,
        patch("souwen.web.search.BingClient") as mock_bing,
    ):
        # Set up async context managers
        for mock_cls, resp in [
            (mock_ddg, ddg_resp),
            (mock_bing, bing_resp),
        ]:
            instance = AsyncMock()
            instance.search = AsyncMock(return_value=resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await web_search("test query")

    assert len(result.results) == 2
    engines = {r.engine for r in result.results}
    assert engines == {"duckduckgo", "bing"}


async def test_web_search_deduplication():
    """web_search 启用去重时移除重复 URL"""
    r1 = _make_result("duckduckgo", "Page", "https://example.com")
    r2 = _make_result("bing", "Page", "https://example.com/")  # trailing slash = same

    ddg_resp = _make_engine_response("duckduckgo", [r1])
    bing_resp = _make_engine_response("bing", [r2])

    with (
        patch("souwen.web.search.DuckDuckGoClient") as mock_ddg,
        patch("souwen.web.search.BingClient") as mock_bing,
    ):
        for mock_cls, resp in [
            (mock_ddg, ddg_resp),
            (mock_bing, bing_resp),
        ]:
            instance = AsyncMock()
            instance.search = AsyncMock(return_value=resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await web_search("test", deduplicate=True)

    assert len(result.results) == 1


async def test_web_search_engine_failure_graceful():
    """单个引擎失败不影响整体"""
    bing_results = [_make_result("bing", "Bing 1", "https://bing1.com")]
    bing_resp = _make_engine_response("bing", bing_results)

    with (
        patch("souwen.web.search.DuckDuckGoClient") as mock_ddg,
        patch("souwen.web.search.BingClient") as mock_bing,
    ):
        # DDG raises exception
        ddg_instance = AsyncMock()
        ddg_instance.search = AsyncMock(side_effect=RuntimeError("DDG down"))
        mock_ddg.return_value.__aenter__ = AsyncMock(return_value=ddg_instance)
        mock_ddg.return_value.__aexit__ = AsyncMock(return_value=False)

        # Bing works
        bing_instance = AsyncMock()
        bing_instance.search = AsyncMock(return_value=bing_resp)
        mock_bing.return_value.__aenter__ = AsyncMock(return_value=bing_instance)
        mock_bing.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await web_search("test")

    assert len(result.results) == 1
    assert result.results[0].engine == "bing"


async def test_web_search_engine_timeout_graceful(monkeypatch):
    """单个引擎超时不影响整体返回。"""
    bing_results = [_make_result("bing", "Bing 1", "https://bing1.com")]
    bing_resp = _make_engine_response("bing", bing_results)

    async def slow_search(*args, **kwargs):
        await asyncio.sleep(0.05)
        return _make_engine_response("duckduckgo", [])

    monkeypatch.setattr("souwen.web.search._get_engine_timeout_seconds", lambda: 0.01)

    with (
        patch("souwen.web.search.DuckDuckGoClient") as mock_ddg,
        patch("souwen.web.search.BingClient") as mock_bing,
    ):
        ddg_instance = AsyncMock()
        ddg_instance.search = AsyncMock(side_effect=slow_search)
        mock_ddg.return_value.__aenter__ = AsyncMock(return_value=ddg_instance)
        mock_ddg.return_value.__aexit__ = AsyncMock(return_value=False)

        bing_instance = AsyncMock()
        bing_instance.search = AsyncMock(return_value=bing_resp)
        mock_bing.return_value.__aenter__ = AsyncMock(return_value=bing_instance)
        mock_bing.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await web_search("test")

    assert len(result.results) == 1
    assert result.results[0].engine == "bing"


async def test_web_search_custom_engines():
    """指定引擎列表时只查询指定引擎"""
    ddg_results = [_make_result("duckduckgo", "DDG 1", "https://ddg1.com")]
    ddg_resp = _make_engine_response("duckduckgo", ddg_results)

    with patch("souwen.web.search.DuckDuckGoClient") as mock_ddg:
        instance = AsyncMock()
        instance.search = AsyncMock(return_value=ddg_resp)
        mock_ddg.return_value.__aenter__ = AsyncMock(return_value=instance)
        mock_ddg.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await web_search("test", engines=["duckduckgo"])

    assert len(result.results) == 1
    assert result.results[0].engine == "duckduckgo"


async def test_web_search_unknown_engine():
    """未知引擎名不崩溃"""
    result = await web_search("test", engines=["nonexistent_engine_xyz"])
    assert result.results == []


def test_web_search_response_model():
    """WebSearchResponse 字段正确"""
    from souwen.models import WebSearchResponse

    resp = WebSearchResponse(
        query="hello",
        source=SourceType.WEB_DUCKDUCKGO,
        results=[
            WebSearchResult(
                source=SourceType.WEB_DUCKDUCKGO,
                title="Hello",
                url="https://hello.com",
                snippet="world",
                engine="duckduckgo",
            )
        ],
        total_results=1,
    )
    assert resp.query == "hello"
    assert resp.total_results == 1
    assert resp.results[0].engine == "duckduckgo"
