"""souwen.web.fetch handler registry 测试。

覆盖：
  - _FETCH_HANDLERS 包含全部 21 个内置 provider
  - register_fetch_handler 新增 / 重名跳过 / override
  - get_fetch_handlers 视图
  - _fetch_with_provider 派发到注册的 handler
  - 未知 provider 返回错误 FetchResponse
  - 外部插件 handler 注册与派发
"""

from __future__ import annotations

import pytest

from souwen.models import FetchResponse, FetchResult
from souwen.web.fetch import (
    _FETCH_HANDLERS,
    _fetch_with_provider,
    get_fetch_handlers,
    register_fetch_handler,
)

EXPECTED_BUILTIN_PROVIDERS = {
    "builtin",
    "jina_reader",
    "arxiv_fulltext",
    "tavily",
    "firecrawl",
    "xcrawl",
    "exa",
    "crawl4ai",
    "scrapfly",
    "diffbot",
    "scrapingbee",
    "zenrows",
    "scraperapi",
    "apify",
    "cloudflare",
    "wayback",
    "newspaper",
    "readability",
    "mcp",
    "site_crawler",
    "deepwiki",
}


def _make_response(provider: str, urls: list[str], ok: bool = True) -> FetchResponse:
    results = [
        FetchResult(
            url=u,
            final_url=u,
            source=provider,
            content="ok" if ok else None,
            error=None if ok else "boom",
        )
        for u in urls
    ]
    n_ok = sum(1 for r in results if r.error is None)
    return FetchResponse(
        urls=urls,
        results=results,
        total=len(results),
        total_ok=n_ok,
        total_failed=len(results) - n_ok,
        provider=provider,
    )


# ── 内置注册表完整性 ───────────────────────────────────────


class TestBuiltinHandlers:
    def test_all_21_providers_registered(self):
        names = set(_FETCH_HANDLERS.keys())
        missing = EXPECTED_BUILTIN_PROVIDERS - names
        assert not missing, f"缺失内置 provider: {missing}"

    def test_handler_count_at_least_21(self):
        # 允许其它插件追加，但内置 21 个必须就位
        assert len(_FETCH_HANDLERS) >= 21

    def test_get_fetch_handlers_returns_copy(self):
        snap = get_fetch_handlers()
        assert isinstance(snap, dict)
        assert set(snap.keys()) >= EXPECTED_BUILTIN_PROVIDERS
        # 修改副本不影响原表
        snap["__bogus__"] = lambda *a, **kw: None  # type: ignore[assignment]
        assert "__bogus__" not in _FETCH_HANDLERS


# ── register_fetch_handler ─────────────────────────────────


class TestRegisterFetchHandler:
    def test_register_new(self, clean_fetch_handlers):
        async def my_handler(urls, timeout, **_):
            return _make_response("my_new", urls)

        register_fetch_handler("my_new", my_handler)
        assert _FETCH_HANDLERS["my_new"] is my_handler

    def test_duplicate_no_override_skips(self, clean_fetch_handlers):
        async def first(urls, timeout, **_):
            return _make_response("dup", urls)

        async def second(urls, timeout, **_):
            return _make_response("dup", urls)

        register_fetch_handler("dup", first)
        register_fetch_handler("dup", second)
        # 重名不覆盖，保留第一个
        assert _FETCH_HANDLERS["dup"] is first

    def test_override_true_replaces(self, clean_fetch_handlers):
        async def first(urls, timeout, **_):
            return _make_response("ovr", urls)

        async def second(urls, timeout, **_):
            return _make_response("ovr2", urls)

        register_fetch_handler("ovr", first)
        register_fetch_handler("ovr", second, override=True)
        assert _FETCH_HANDLERS["ovr"] is second


# ── _fetch_with_provider ───────────────────────────────────


class TestFetchWithProvider:
    @pytest.mark.asyncio
    async def test_dispatches_to_registered_handler(self, clean_fetch_handlers):
        called = {}

        async def my_handler(urls, timeout, **kwargs):
            called["urls"] = urls
            called["timeout"] = timeout
            called["kwargs"] = kwargs
            return _make_response("dispatch_test", urls)

        register_fetch_handler("dispatch_test", my_handler)
        resp = await _fetch_with_provider("dispatch_test", ["http://example.com"], 5.0, foo="bar")
        assert resp.provider == "dispatch_test"
        assert called["urls"] == ["http://example.com"]
        assert called["timeout"] == 5.0
        assert called["kwargs"] == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_unknown_provider_returns_error_response(self):
        urls = ["http://a.example", "http://b.example"]
        resp = await _fetch_with_provider("does_not_exist_xyz", urls, 1.0)
        assert resp.provider == "does_not_exist_xyz"
        assert resp.total == 2
        assert resp.total_ok == 0
        assert resp.total_failed == 2
        for r in resp.results:
            assert r.error is not None
            assert "未知提供者" in r.error

    @pytest.mark.asyncio
    async def test_external_plugin_handler_dispatches(self, clean_fetch_handlers):
        async def ext_handler(urls, timeout, **_):
            return _make_response("ext_via_plugin", urls)

        # 模拟外部插件在加载时调用 register_fetch_handler
        register_fetch_handler("ext_via_plugin", ext_handler)
        resp = await _fetch_with_provider("ext_via_plugin", ["http://x.example"], 2.0)
        assert resp.provider == "ext_via_plugin"
        assert resp.total_ok == 1
