"""聚合搜索容错测试。

覆盖 ``souwen.search`` 中搜索聚合的容错机制与并发安全。
验证超时跳过、信号量事件循环隔离、数据源超时不阻塞等不变量。

v1 改造：测试注入用 `_inject_test_adapter` 向 registry 加临时 adapter
（替代 v0 的 `monkeypatch.setitem(_PAPER_SOURCES, ...)`）。
"""

from __future__ import annotations

import asyncio
import importlib
from contextlib import AsyncExitStack, asynccontextmanager

from souwen.models import SearchResponse
from souwen.registry.adapter import MethodSpec, SourceAdapter


def _make_fake_client(response: SearchResponse, delay: float = 0.0):
    """构造一个异步上下文管理器风格的 fake client 类。"""

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def search(self, **kwargs):
            if delay:
                await asyncio.sleep(delay)
            return response

    return _FakeClient


@asynccontextmanager
async def _temp_adapter(adapter: SourceAdapter):
    """临时把一个 adapter 插入 registry，作用域结束后移除。

    直接操作 views._REGISTRY；生产代码不要这么用。
    """
    from souwen.registry import views

    existing = views._REGISTRY.get(adapter.name)
    views._REGISTRY[adapter.name] = adapter
    try:
        yield
    finally:
        if existing is None:
            views._REGISTRY.pop(adapter.name, None)
        else:
            views._REGISTRY[adapter.name] = existing


async def test_search_papers_skips_timed_out_source(monkeypatch):
    """慢论文源超时时不应阻塞整体结果。"""
    search_mod = importlib.import_module("souwen.search")

    fast_resp = SearchResponse(query="test", source="openalex", results=[], total_results=0)
    slow_resp = SearchResponse(query="test", source="crossref", results=[], total_results=0)
    FastClient = _make_fake_client(fast_resp, delay=0.0)
    SlowClient = _make_fake_client(slow_resp, delay=0.05)

    fast_adapter = SourceAdapter(
        name="fast_test_source",
        domain="paper",
        integration="open_api",
        description="",
        config_field=None,
        client_loader=lambda: FastClient,
        methods={"search": MethodSpec("search")},
    )
    slow_adapter = SourceAdapter(
        name="slow_test_source",
        domain="paper",
        integration="open_api",
        description="",
        config_field=None,
        client_loader=lambda: SlowClient,
        methods={"search": MethodSpec("search")},
    )

    monkeypatch.setattr(search_mod, "_get_source_timeout_seconds", lambda: 0.01)

    async with AsyncExitStack() as stack:
        await stack.enter_async_context(_temp_adapter(fast_adapter))
        await stack.enter_async_context(_temp_adapter(slow_adapter))
        resp = await search_mod.search_papers(
            "test",
            sources=["fast_test_source", "slow_test_source"],
        )

    assert len(resp) == 1
    assert resp[0].source == "openalex"


async def test_search_patents_skips_timed_out_source(monkeypatch):
    """慢专利源超时时不应阻塞整体结果。"""
    search_mod = importlib.import_module("souwen.search")

    fast_resp = SearchResponse(query="test", source="patentsview", results=[], total_results=0)
    slow_resp = SearchResponse(query="test", source="pqai", results=[], total_results=0)
    FastClient = _make_fake_client(fast_resp, delay=0.0)
    SlowClient = _make_fake_client(slow_resp, delay=0.05)

    fast_adapter = SourceAdapter(
        name="fast_test_patent_source",
        domain="patent",
        integration="open_api",
        description="",
        config_field=None,
        client_loader=lambda: FastClient,
        methods={"search": MethodSpec("search")},
    )
    slow_adapter = SourceAdapter(
        name="slow_test_patent_source",
        domain="patent",
        integration="open_api",
        description="",
        config_field=None,
        client_loader=lambda: SlowClient,
        methods={"search": MethodSpec("search")},
    )

    monkeypatch.setattr(search_mod, "_get_source_timeout_seconds", lambda: 0.01)

    async with AsyncExitStack() as stack:
        await stack.enter_async_context(_temp_adapter(fast_adapter))
        await stack.enter_async_context(_temp_adapter(slow_adapter))
        resp = await search_mod.search_patents(
            "test",
            sources=["fast_test_patent_source", "slow_test_patent_source"],
        )

    assert len(resp) == 1
    assert resp[0].source == "patentsview"


async def test_search_dispatches_with_resolved_adapters(monkeypatch):
    """顶层 ``search()`` 应按 domain/capability 选择 adapter 并执行。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}
    sentinel_adapter = object()

    def fake_select(domain, capability, sources):
        captured["select"] = (domain, capability, sources)
        return [sentinel_adapter]

    async def fake_execute(domain, query, adapters, limit, capability, **kwargs):
        captured["execute"] = {
            "domain": domain,
            "query": query,
            "adapters": adapters,
            "limit": limit,
            "capability": capability,
            "kwargs": kwargs,
        }
        return [SearchResponse(query=query, source="openalex", results=[])]

    monkeypatch.setattr(search_mod, "_select_adapters", fake_select)
    monkeypatch.setattr(search_mod, "_execute_search", fake_execute)

    out = await search_mod.search(
        "transformers",
        domain="paper",
        capability="search",
        sources=["openalex"],
        limit=7,
        extra_flag=True,
    )

    assert len(out) == 1
    assert captured["select"] == ("paper", "search", ["openalex"])
    assert captured["execute"]["domain"] == "paper"
    assert captured["execute"]["adapters"] == [sentinel_adapter]
    assert captured["execute"]["limit"] == 7
    assert captured["execute"]["capability"] == "search"
    assert captured["execute"]["kwargs"] == {"extra_flag": True}


async def test_search_papers_targets_paper_domain(monkeypatch):
    """``search_papers()`` 只负责把参数映射到顶层 ``search()``。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}

    async def fake_search(query, domain="paper", capability="search", sources=None, limit=10, **kw):
        captured["args"] = (query, domain, capability, sources, limit, kw)
        return []

    monkeypatch.setattr(search_mod, "search", fake_search)
    await search_mod.search_papers("LLM", sources=["openalex"], per_page=5, lang="zh")

    assert captured["args"] == (
        "LLM",
        "paper",
        "search",
        ["openalex"],
        5,
        {"lang": "zh"},
    )


async def test_search_patents_targets_patent_domain(monkeypatch):
    """``search_patents()`` 只负责把参数映射到顶层 ``search()``。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}

    async def fake_search(query, domain="paper", capability="search", sources=None, limit=10, **kw):
        captured["args"] = (query, domain, capability, sources, limit, kw)
        return []

    monkeypatch.setattr(search_mod, "search", fake_search)
    await search_mod.search_patents("battery", sources=["google_patents"], per_page=3)

    assert captured["args"] == (
        "battery",
        "patent",
        "search",
        ["google_patents"],
        3,
        {},
    )


async def test_search_by_capability_uses_capability_view(monkeypatch):
    """``search_by_capability()`` 应直接使用 registry capability 视图。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}
    sentinel_adapter = object()

    monkeypatch.setattr(search_mod, "by_capability", lambda capability: [sentinel_adapter])

    async def fake_execute(domain, query, adapters, limit, capability, **kwargs):
        captured["execute"] = (domain, query, adapters, limit, capability, kwargs)
        return []

    monkeypatch.setattr(search_mod, "_execute_search", fake_execute)

    await search_mod.search_by_capability("q", "search_news", limit=4, region="cn")

    assert captured["execute"] == (
        "*",
        "q",
        [sentinel_adapter],
        4,
        "search_news",
        {"region": "cn"},
    )


async def test_search_news_uses_registry_default(monkeypatch):
    """README 示例里的 web/search_news 无 sources 调用应有默认源。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}

    async def fake_execute(domain, query, adapters, limit, capability, **kwargs):
        captured["execute"] = (domain, query, [a.name for a in adapters], limit, capability, kwargs)
        return []

    monkeypatch.setattr(search_mod, "_execute_search", fake_execute)

    await search_mod.search("AI news", domain="web", capability="search_news", limit=4)

    assert captured["execute"] == (
        "web",
        "AI news",
        ["duckduckgo_news"],
        4,
        "search_news",
        {},
    )


async def test_search_all_groups_domain_results(monkeypatch):
    """``search_all()`` 应并发调用顶层 ``search`` 并按 domain 分组。"""
    search_mod = importlib.import_module("souwen.search")
    calls = []

    async def fake_search(query, domain="paper", **kwargs):
        calls.append((query, domain, kwargs))
        return [SearchResponse(query=query, source="openalex", results=[])]

    monkeypatch.setattr(search_mod, "search", fake_search)

    out = await search_mod.search_all("agent", domains=["paper", "web"], per_domain_limit=2)

    assert sorted(out) == ["paper", "web"]
    assert calls == [
        ("agent", "paper", {"limit": 2}),
        ("agent", "web", {"limit": 2}),
    ]


def test_semaphore_is_per_event_loop():
    """_get_semaphore 在不同 event loop 中返回不同实例，避免跨 loop 错误。

    v1：改由 `core.concurrency.get_semaphore('search')` 实现，走
    WeakKeyDictionary[loop, Semaphore] 保证 per-loop 隔离。
    """
    search_mod = importlib.import_module("souwen.search")

    async def _fetch() -> asyncio.Semaphore:
        return search_mod._get_semaphore()

    loop1 = asyncio.new_event_loop()
    try:
        sem1 = loop1.run_until_complete(_fetch())
        sem1_again = loop1.run_until_complete(_fetch())
    finally:
        loop1.close()

    loop2 = asyncio.new_event_loop()
    try:
        sem2 = loop2.run_until_complete(_fetch())
    finally:
        loop2.close()

    assert sem1 is sem1_again
    assert sem1 is not sem2
