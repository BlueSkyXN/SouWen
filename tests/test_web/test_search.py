"""Web 聚合搜索单元测试（v1 registry 适配版）。

v0 测试用 `patch("souwen.web.search.DuckDuckGoClient")` mock 顶层 import；
v1 的 web_search() 通过 `souwen.registry` 动态加载 Client，所以改用
`_temp_adapter` 临时插入 fake adapter 来隔离真实网络调用。

测试清单：
- _deduplicate 三个（URL 去重逻辑，与 v1 无关）
- web_search 聚合 / 去重 / 错误隔离 / 超时 / 未知引擎 / 自定义引擎（全改 registry）
- WebSearchResponse 字段正确
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from souwen.models import SearchResponse, SourceType, WebSearchResult
from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.web.search import _deduplicate, web_search


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(engine: str, title: str, url: str) -> WebSearchResult:
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


def _make_fake_client_class(search_resp=None, search_exc=None, search_side_effect=None):
    """生成一个假的 Client 类（async context manager）。"""

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def search(self, query, max_results=10, **kwargs):
            if search_side_effect is not None:
                return await search_side_effect(query, max_results=max_results, **kwargs)
            if search_exc is not None:
                raise search_exc
            return search_resp

    return _FakeClient


@asynccontextmanager
async def _override_adapters(name_to_client: dict[str, type]):
    """临时把 registry 里 adapter 的 client_loader 改为 fake client。"""
    from souwen.registry import views

    originals: dict[str, SourceAdapter] = {}
    for name, fake_cls in name_to_client.items():
        orig = views._REGISTRY.get(name)
        if orig is None:
            # 建一个最小 adapter
            new = SourceAdapter(
                name=name,
                domain="web",
                integration="scraper",
                description="",
                config_field=None,
                client_loader=lambda cls=fake_cls: cls,
                methods={"search": MethodSpec("search")},
            )
        else:
            # 用 fake_cls 替换 client_loader；其他属性保留
            originals[name] = orig
            # dataclass(frozen) 复制时替换 client_loader
            import dataclasses

            new = dataclasses.replace(orig, client_loader=lambda cls=fake_cls: cls)
        views._REGISTRY[name] = new
    try:
        yield
    finally:
        for name, orig in originals.items():
            views._REGISTRY[name] = orig
        # 对于原本不存在的 adapter，清掉
        for name in name_to_client:
            if name not in originals:
                views._REGISTRY.pop(name, None)


# ---------------------------------------------------------------------------
# _deduplicate tests
# ---------------------------------------------------------------------------


def test_deduplicate_removes_duplicates():
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
    results = [
        _make_result("duckduckgo", "A", "https://Example.COM/Page"),
        _make_result("bing", "B", "https://example.com/page"),
    ]
    assert len(_deduplicate(results)) == 1


def test_deduplicate_empty():
    assert _deduplicate([]) == []


# ---------------------------------------------------------------------------
# web_search aggregation tests (v1: 通过 _override_adapters mock)
# ---------------------------------------------------------------------------


async def test_web_search_aggregates_engines():
    ddg_resp = _make_engine_response("duckduckgo", [_make_result("duckduckgo", "DDG 1", "https://ddg1.com")])
    bing_resp = _make_engine_response("bing", [_make_result("bing", "Bing 1", "https://bing1.com")])

    async with _override_adapters({
        "duckduckgo": _make_fake_client_class(search_resp=ddg_resp),
        "bing": _make_fake_client_class(search_resp=bing_resp),
    }):
        result = await web_search("test query")

    assert len(result.results) == 2
    engines = {r.engine for r in result.results}
    assert engines == {"duckduckgo", "bing"}


async def test_web_search_deduplication():
    r1 = _make_result("duckduckgo", "Page", "https://example.com")
    r2 = _make_result("bing", "Page", "https://example.com/")
    ddg_resp = _make_engine_response("duckduckgo", [r1])
    bing_resp = _make_engine_response("bing", [r2])

    async with _override_adapters({
        "duckduckgo": _make_fake_client_class(search_resp=ddg_resp),
        "bing": _make_fake_client_class(search_resp=bing_resp),
    }):
        result = await web_search("test", deduplicate=True)

    assert len(result.results) == 1


async def test_web_search_engine_failure_graceful():
    bing_resp = _make_engine_response("bing", [_make_result("bing", "Bing 1", "https://bing1.com")])

    async with _override_adapters({
        "duckduckgo": _make_fake_client_class(search_exc=RuntimeError("DDG down")),
        "bing": _make_fake_client_class(search_resp=bing_resp),
    }):
        result = await web_search("test")

    assert len(result.results) == 1
    assert result.results[0].engine == "bing"


async def test_web_search_engine_timeout_graceful(monkeypatch):
    bing_resp = _make_engine_response("bing", [_make_result("bing", "Bing 1", "https://bing1.com")])

    async def slow_search(query, max_results=10, **kwargs):
        await asyncio.sleep(0.05)
        return _make_engine_response("duckduckgo", [])

    monkeypatch.setattr("souwen.web.search._get_engine_timeout_seconds", lambda: 0.01)

    async with _override_adapters({
        "duckduckgo": _make_fake_client_class(search_side_effect=slow_search),
        "bing": _make_fake_client_class(search_resp=bing_resp),
    }):
        result = await web_search("test")

    assert len(result.results) == 1
    assert result.results[0].engine == "bing"


async def test_web_search_custom_engines():
    ddg_resp = _make_engine_response("duckduckgo", [_make_result("duckduckgo", "DDG 1", "https://ddg1.com")])

    async with _override_adapters({
        "duckduckgo": _make_fake_client_class(search_resp=ddg_resp),
    }):
        result = await web_search("test", engines=["duckduckgo"])

    assert len(result.results) == 1
    assert result.results[0].engine == "duckduckgo"


async def test_web_search_unknown_engine():
    """未知引擎名不崩溃。"""
    result = await web_search("test", engines=["nonexistent_engine_xyz"])
    assert result.results == []


def test_web_search_response_model():
    """WebSearchResponse 字段正确。"""
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
