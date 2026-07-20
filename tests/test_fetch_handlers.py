"""souwen.web.fetch handler registry 测试。

覆盖：
  - _FETCH_HANDLERS 包含全部 24 个内置 provider
  - register_fetch_handler 新增 / 重名跳过 / override
  - get_fetch_handlers 视图
  - _fetch_with_provider 派发到注册的 handler
  - 未知 provider 返回错误 FetchResponse
  - 外部插件 handler 注册与派发
"""

from __future__ import annotations

import json

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
    "kimi_code",
    "exa",
    "metaso",
    "crawl4ai",
    "scrapling",
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
    def test_all_24_providers_registered(self):
        names = set(_FETCH_HANDLERS.keys())
        missing = EXPECTED_BUILTIN_PROVIDERS - names
        assert not missing, f"缺失内置 provider: {missing}"

    def test_handler_count_at_least_24(self):
        # 允许其它插件追加，但内置 24 个必须就位
        assert len(_FETCH_HANDLERS) >= 24

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
        assert _FETCH_HANDLERS["my_new"].handler is my_handler

    def test_duplicate_no_override_skips(self, clean_fetch_handlers):
        async def first(urls, timeout, **_):
            return _make_response("dup", urls)

        async def second(urls, timeout, **_):
            return _make_response("dup", urls)

        register_fetch_handler("dup", first)
        register_fetch_handler("dup", second)
        # 重名不覆盖，保留第一个
        assert _FETCH_HANDLERS["dup"].handler is first

    def test_override_true_replaces(self, clean_fetch_handlers):
        async def first(urls, timeout, **_):
            return _make_response("ovr", urls)

        async def second(urls, timeout, **_):
            return _make_response("ovr2", urls)

        register_fetch_handler("ovr", first)
        register_fetch_handler("ovr", second, override=True)
        assert _FETCH_HANDLERS["ovr"].handler is second


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
    async def test_dispatch_filters_unknown_kwargs_for_legacy_handler(self, clean_fetch_handlers):
        called = {}

        async def legacy_handler(urls, timeout):
            called["urls"] = urls
            called["timeout"] = timeout
            return _make_response("legacy_handler", urls)

        register_fetch_handler("legacy_handler", legacy_handler)
        resp = await _fetch_with_provider(
            "legacy_handler",
            ["http://example.com"],
            5.0,
            selector="article",
            start_index=20,
        )

        assert resp.provider == "legacy_handler"
        assert called == {"urls": ["http://example.com"], "timeout": 5.0}

    @pytest.mark.asyncio
    async def test_dispatch_passes_named_supported_kwargs(self, clean_fetch_handlers):
        called = {}

        async def selective_handler(urls, timeout, selector=None):
            called["urls"] = urls
            called["timeout"] = timeout
            called["selector"] = selector
            return _make_response("selective_handler", urls)

        register_fetch_handler("selective_handler", selective_handler)
        resp = await _fetch_with_provider(
            "selective_handler",
            ["http://example.com"],
            5.0,
            selector="article",
            start_index=20,
        )

        assert resp.provider == "selective_handler"
        assert called == {
            "urls": ["http://example.com"],
            "timeout": 5.0,
            "selector": "article",
        }

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

    @pytest.mark.asyncio
    async def test_metaso_handler_dispatches_reader(self, httpx_mock, monkeypatch):
        monkeypatch.setenv("SOUWEN_METASO_API_KEY", "mk-test")
        target_url = "https://93.184.216.34/article"
        httpx_mock.add_response(
            url="https://metaso.cn/api/v1/reader",
            content=b"metaso reader content",
            headers={"Content-Type": "text/plain"},
        )

        resp = await _fetch_with_provider("metaso", [target_url], 5.0)

        assert resp.provider == "metaso"
        assert resp.total == 1
        assert resp.total_ok == 1
        assert resp.results[0].source == "metaso"
        assert resp.results[0].content == "metaso reader content"

        req = httpx_mock.get_requests()[0]
        assert req.headers.get("authorization") == "Bearer mk-test"
        assert json.loads(req.content)["url"] == target_url
