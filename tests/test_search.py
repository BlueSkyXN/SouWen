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

import pytest

from souwen.editions import EditionError
from souwen.core.exceptions import LocalCatalogUnavailableError
from souwen.models import SearchResponse, WaybackCDXResponse
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


async def test_explicit_single_local_catalog_unavailable_is_not_reported_as_empty_result():
    """Explicit local catalog requests must provide a recoverable failure, not a false empty hit."""
    search_mod = importlib.import_module("souwen.search")

    class UnavailableClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def search(self, **_kwargs):
            raise LocalCatalogUnavailableError("local catalog is not initialized")

    adapter = SourceAdapter(
        name="local_catalog_unavailable_probe",
        domain="book",
        integration="official_api",
        description="",
        config_field=None,
        client_loader=lambda: UnavailableClient,
        methods={"search": MethodSpec("search")},
    )
    async with _temp_adapter(adapter):
        with pytest.raises(LocalCatalogUnavailableError):
            await search_mod.search_books("Alice", sources=[adapter.name])


async def test_local_catalog_unavailable_does_not_block_other_explicit_sources():
    search_mod = importlib.import_module("souwen.search")

    class UnavailableClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def search(self, **_kwargs):
            raise LocalCatalogUnavailableError("local catalog is not initialized")

    available = SearchResponse(query="Alice", source="available_book_probe", results=[])
    unavailable_adapter = SourceAdapter(
        name="local_catalog_unavailable_mixed_probe",
        domain="book",
        integration="official_api",
        description="",
        config_field=None,
        client_loader=lambda: UnavailableClient,
        methods={"search": MethodSpec("search")},
    )
    available_adapter = SourceAdapter(
        name="available_book_probe",
        domain="book",
        integration="official_api",
        description="",
        config_field=None,
        client_loader=lambda: _make_fake_client(available),
        methods={"search": MethodSpec("search")},
    )
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(_temp_adapter(unavailable_adapter))
        await stack.enter_async_context(_temp_adapter(available_adapter))
        results = await search_mod.search_books(
            "Alice", sources=[unavailable_adapter.name, available_adapter.name]
        )
    assert [response.source for response in results] == [available_adapter.name]


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


async def test_search_sources_string_is_normalized(monkeypatch):
    """单个 sources 字符串不应被拆成字符。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}

    async def fake_execute(domain, query, adapters, limit, capability, **kwargs):
        captured["execute"] = [adapter.name for adapter in adapters]
        return []

    monkeypatch.setattr(search_mod, "_execute_search", fake_execute)

    await search_mod.search("transformers", domain="paper", sources=" openalex ")

    assert captured["execute"] == ["openalex"]


def test_select_adapters_filters_default_sources_by_edition(monkeypatch):
    """默认源选择应按当前 edition 静默过滤不可用 source。"""
    search_mod = importlib.import_module("souwen.search")
    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    monkeypatch.setattr(
        search_mod, "defaults_for", lambda _domain, _capability: ["arxiv", "openalex"]
    )

    adapters = search_mod._select_adapters("paper", "search", None)

    assert [adapter.name for adapter in adapters] == ["arxiv"]


def test_select_adapters_explicit_disallowed_source_raises(monkeypatch):
    """显式点名当前 edition 不包含的 source 应直接报 EditionError。"""
    search_mod = importlib.import_module("souwen.search")
    monkeypatch.setenv("SOUWEN_EDITION", "basic")

    with pytest.raises(EditionError, match="source 'openalex' requires edition=pro"):
        search_mod._select_adapters("paper", "search", ["openalex"])


async def test_search_query_is_trimmed_before_dispatch(monkeypatch):
    """顶层 ``search()`` 应裁剪 query 后再派发到 provider。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}

    async def fake_execute(domain, query, adapters, limit, capability, **kwargs):
        captured["query"] = query
        return [SearchResponse(query=query, source="openalex", results=[])]

    monkeypatch.setattr(search_mod, "_execute_search", fake_execute)

    out = await search_mod.search("  transformers  ", domain="paper", sources=["openalex"])

    assert captured["query"] == "transformers"
    assert out[0].query == "transformers"


@pytest.mark.parametrize("query", ["", "   ", 123])
async def test_search_invalid_query_arguments_raise_clear_error(query):
    """顶层 ``search()`` 应拒绝非字符串或 strip 后为空的 query。"""
    search_mod = importlib.import_module("souwen.search")

    with pytest.raises(ValueError, match="query"):
        await search_mod.search(query, domain="paper", sources=["openalex"])


@pytest.mark.parametrize(
    "sources",
    ["", ["openalex", ""], ["openalex", 123], object()],
)
async def test_search_sources_invalid_arguments_raise_clear_error(sources):
    search_mod = importlib.import_module("souwen.search")

    with pytest.raises(ValueError, match="sources"):
        await search_mod.search("transformers", domain="paper", sources=sources)


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


@pytest.mark.parametrize(
    ("func_name", "expected_domain"),
    [("search_papers", "paper"), ("search_patents", "patent")],
)
async def test_domain_search_helpers_trim_query_before_delegating(
    monkeypatch, func_name, expected_domain
):
    """``search_papers()`` / ``search_patents()`` 应先裁剪 query 再委托顶层 search。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}

    async def fake_search(query, domain="paper", capability="search", sources=None, limit=10, **kw):
        captured["args"] = (query, domain, capability, sources, limit, kw)
        return []

    monkeypatch.setattr(search_mod, "search", fake_search)
    await getattr(search_mod, func_name)("  graph rag  ", sources=["openalex"], per_page=5)

    assert captured["args"][0] == "graph rag"
    assert captured["args"][1] == expected_domain


async def test_search_by_capability_uses_capability_view(monkeypatch):
    """``search_by_capability()`` 应直接使用 registry capability 视图。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}
    sentinel_adapter = SourceAdapter(
        name="sentinel_search_news",
        domain="web",
        integration="scraper",
        description="",
        config_field=None,
        client_loader=lambda: object,
        methods={"search_news": MethodSpec("search")},
    )

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


async def test_search_by_capability_sources_string_is_normalized(monkeypatch):
    """``search_by_capability()`` 也接受单个 source 字符串。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}

    async def fake_execute(domain, query, adapters, limit, capability, **kwargs):
        captured["execute"] = [adapter.name for adapter in adapters]
        return []

    monkeypatch.setattr(search_mod, "_execute_search", fake_execute)

    await search_mod.search_by_capability("q", "search", sources=" openalex ")

    assert captured["execute"] == ["openalex"]


async def test_search_by_capability_query_is_trimmed_before_dispatch(monkeypatch):
    """``search_by_capability()`` 应裁剪 query 后再派发。"""
    search_mod = importlib.import_module("souwen.search")
    captured = {}

    async def fake_execute(domain, query, adapters, limit, capability, **kwargs):
        captured["query"] = query
        return []

    monkeypatch.setattr(search_mod, "_execute_search", fake_execute)

    await search_mod.search_by_capability("  AI news  ", "search", sources="openalex")

    assert captured["query"] == "AI news"


async def test_search_by_capability_filters_default_sources_by_edition(monkeypatch):
    """跨 domain capability 默认选择也必须按 edition 过滤。"""
    search_mod = importlib.import_module("souwen.search")
    from souwen.registry import get as registry_get

    adapters = [registry_get("arxiv"), registry_get("openalex")]
    assert all(adapters)
    captured = {}

    async def fake_execute(domain, query, adapters, limit, capability, **kwargs):
        captured["execute"] = [adapter.name for adapter in adapters]
        return []

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    monkeypatch.setattr(search_mod, "by_capability", lambda _capability: adapters)
    monkeypatch.setattr(search_mod, "_execute_search", fake_execute)

    await search_mod.search_by_capability("q", "search")

    assert captured["execute"] == ["arxiv"]


async def test_search_by_capability_explicit_disallowed_source_raises(monkeypatch):
    """跨 domain capability 显式点名不可用 source 时也必须拒绝。"""
    search_mod = importlib.import_module("souwen.search")
    monkeypatch.setenv("SOUWEN_EDITION", "basic")

    with pytest.raises(EditionError, match="source 'openalex' requires edition=pro"):
        await search_mod.search_by_capability("q", "search", sources="openalex")


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


async def test_archive_lookup_maps_query_to_url_and_keeps_non_search_response():
    """``archive:archive_lookup`` 不能收到 search 专用的 ``query`` 参数。"""
    search_mod = importlib.import_module("souwen.search")
    calls = []

    class FakeArchiveClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def query_snapshots(self, url: str, limit: int | None = None, from_date=None):
            calls.append({"url": url, "limit": limit, "from_date": from_date})
            return WaybackCDXResponse(url=url, total=0, from_date=from_date)

    adapter = SourceAdapter(
        name="fake_archive_lookup",
        domain="archive",
        integration="open_api",
        description="",
        config_field=None,
        client_loader=lambda: FakeArchiveClient,
        methods={"archive_lookup": MethodSpec("query_snapshots")},
    )

    async with _temp_adapter(adapter):
        resp = await search_mod.search(
            "https://example.com",
            domain="archive",
            capability="archive_lookup",
            sources=["fake_archive_lookup"],
            limit=3,
            from_date="20240101",
        )

    assert calls == [
        {
            "url": "https://example.com",
            "limit": 3,
            "from_date": "20240101",
        }
    ]
    assert len(resp) == 1
    assert isinstance(resp[0], WaybackCDXResponse)
    assert resp[0].url == "https://example.com"


async def test_get_trending_does_not_receive_query_argument():
    """``video:get_trending`` 是无 query 能力，只应收到 limit 映射后的参数。"""
    search_mod = importlib.import_module("souwen.search")
    calls = []

    class FakeTrendingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get_trending(self, region_code: str = "US", max_results: int = 10):
            calls.append({"region_code": region_code, "max_results": max_results})
            return SearchResponse(query=f"trending:{region_code}", source="youtube", results=[])

    adapter = SourceAdapter(
        name="fake_video_trending",
        domain="video",
        integration="open_api",
        description="",
        config_field=None,
        client_loader=lambda: FakeTrendingClient,
        methods={"get_trending": MethodSpec("get_trending", {"limit": "max_results"})},
    )

    async with _temp_adapter(adapter):
        resp = await search_mod.search(
            "ignored",
            domain="video",
            capability="get_trending",
            sources=["fake_video_trending"],
            limit=5,
            region_code="JP",
        )

    assert calls == [{"region_code": "JP", "max_results": 5}]
    assert len(resp) == 1
    assert resp[0].source == "youtube"


async def test_fetch_capability_uses_target_signature_for_query_and_limit():
    """``fetch`` provider 需要 ``urls`` 时，应把 query 包成列表且不硬塞 limit。"""
    search_mod = importlib.import_module("souwen.search")
    calls = []

    class FakeBatchFetchClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def fetch_batch(self, urls: list[str]):
            calls.append({"urls": urls})
            return {"provider": "fake_batch_fetch", "urls": urls}

    adapter = SourceAdapter(
        name="fake_batch_fetch",
        domain="fetch",
        integration="open_api",
        description="",
        config_field=None,
        client_loader=lambda: FakeBatchFetchClient,
        methods={"fetch": MethodSpec("fetch_batch")},
    )

    async with _temp_adapter(adapter):
        resp = await search_mod.search(
            "https://example.com",
            domain="fetch",
            capability="fetch",
            sources=["fake_batch_fetch"],
            limit=99,
        )

    assert calls == [{"urls": ["https://example.com"]}]
    assert resp == [{"provider": "fake_batch_fetch", "urls": ["https://example.com"]}]


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


async def test_search_all_domain_string_is_normalized(monkeypatch):
    """单个 domains 字符串不应被拆成字符。"""
    search_mod = importlib.import_module("souwen.search")
    calls = []

    async def fake_search(query, domain="paper", **kwargs):
        calls.append((query, domain, kwargs))
        return [SearchResponse(query=query, source="openalex", results=[])]

    monkeypatch.setattr(search_mod, "search", fake_search)

    out = await search_mod.search_all("agent", domains=" paper ", per_domain_limit=2)

    assert sorted(out) == ["paper"]
    assert calls == [("agent", "paper", {"limit": 2})]


async def test_search_all_query_is_trimmed_before_delegating(monkeypatch):
    """``search_all()`` 应裁剪 query 后再委托各 domain 搜索。"""
    search_mod = importlib.import_module("souwen.search")
    calls = []

    async def fake_search(query, domain="paper", **kwargs):
        calls.append((query, domain, kwargs))
        return [SearchResponse(query=query, source="openalex", results=[])]

    monkeypatch.setattr(search_mod, "search", fake_search)

    out = await search_mod.search_all("  agent  ", domains=["paper"], per_domain_limit=2)

    assert calls[0][0] == "agent"
    assert out["paper"][0].query == "agent"


async def test_search_all_empty_domains_uses_defaults(monkeypatch):
    """保持既有行为：空 domains 列表沿用默认聚合域。"""
    search_mod = importlib.import_module("souwen.search")
    calls = []

    async def fake_search(query, domain="paper", **kwargs):
        calls.append(domain)
        return []

    monkeypatch.setattr(search_mod, "search", fake_search)
    monkeypatch.setattr(search_mod, "DEFAULT_AGGREGATE_DOMAINS", ("paper", "web"))

    out = await search_mod.search_all("agent", domains=[])

    assert sorted(out) == ["paper", "web"]
    assert calls == ["paper", "web"]


@pytest.mark.parametrize(
    "domains",
    ["", ["paper", ""], ["paper", 123], object()],
)
async def test_search_all_invalid_domains_raise_clear_error(domains):
    search_mod = importlib.import_module("souwen.search")

    with pytest.raises(ValueError, match="domains"):
        await search_mod.search_all("agent", domains=domains)


async def test_search_all_accepts_limit_alias(monkeypatch):
    """兼容公开示例中使用的 ``limit`` 别名，避免被 **kwargs 重复传参吞空。"""
    search_mod = importlib.import_module("souwen.search")
    calls = []

    async def fake_search(query, domain="paper", **kwargs):
        calls.append((query, domain, kwargs))
        return [SearchResponse(query=query, source="openalex", results=[])]

    monkeypatch.setattr(search_mod, "search", fake_search)

    out = await search_mod.search_all("agent", domains=["paper"], limit=3)

    assert sorted(out) == ["paper"]
    assert calls == [("agent", "paper", {"limit": 3})]


async def test_search_all_rejects_conflicting_limit_alias():
    """两个限制参数同时传且值不同应显式失败。"""
    search_mod = importlib.import_module("souwen.search")

    try:
        await search_mod.search_all("agent", domains=["paper"], per_domain_limit=2, limit=3)
    except ValueError as exc:
        assert "per_domain_limit 和 limit" in str(exc)
    else:  # pragma: no cover - 失败路径
        raise AssertionError("search_all() should reject conflicting limits")


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
