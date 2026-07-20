"""``POST /api/v1/fetch`` 路由测试。

覆盖 ``souwen.server.routes.fetch.fetch_content_endpoint`` 的请求校验
与正常路径：合法请求返回 200、必填字段缺失返回 422、provider 不在白名单
返回 400、timeout 越界由 Pydantic 校验返回 422。所有测试通过 monkeypatch
``souwen.web.fetch.fetch_content`` 桩掉真正的网络抓取。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from souwen.models import FetchResponse, FetchResult


@pytest.fixture(autouse=True)
def isolated_search_limiter(monkeypatch):
    from souwen.server import limiter as limiter_mod

    monkeypatch.setattr(
        limiter_mod,
        "_search_limiter",
        limiter_mod.InMemoryRateLimiter(max_requests=60, window_seconds=60),
    )


@pytest.fixture()
def client(monkeypatch):
    """显式开放 admin 的 TestClient，用于聚焦 fetch 入参校验。"""
    monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def stub_fetch(monkeypatch):
    """把 ``souwen.web.fetch.fetch_content`` 替换为内存桩，避免网络访问。"""
    calls: list[dict] = []

    async def _fake_fetch(
        urls,
        providers=None,
        strategy="fallback",
        timeout=30.0,
        selector=None,
        start_index=0,
        max_length=None,
        respect_robots_txt=False,
    ):
        calls.append(
            {
                "urls": list(urls),
                "providers": list(providers) if providers else providers,
                "strategy": strategy,
                "timeout": timeout,
                "selector": selector,
                "start_index": start_index,
                "max_length": max_length,
                "respect_robots_txt": respect_robots_txt,
            }
        )
        results = [
            FetchResult(
                url=u,
                final_url=u,
                title="stub",
                content="stub-content",
                source=(providers[0] if providers else "builtin"),
            )
            for u in urls
        ]
        return FetchResponse(
            urls=list(urls),
            results=results,
            total=len(results),
            total_ok=len(results),
            total_failed=0,
            provider=(
                providers[0]
                if providers and len(providers) == 1
                else None
                if providers
                else "builtin"
            ),
            providers=list(providers) if providers else ["builtin"],
            strategy=strategy,
        )

    import souwen.web.fetch as web_fetch_mod

    monkeypatch.setattr(web_fetch_mod, "fetch_content", _fake_fetch)
    return calls


@pytest.fixture()
def stub_link_tools(monkeypatch):
    """桩掉链接提取下游，聚焦 route query 参数归一化。"""
    from souwen.web.links import LinkExtractionResult

    calls: list[dict] = []

    async def _fake_extract_links(url, base_url_filter=None, limit=100):
        calls.append(
            {
                "url": url,
                "base_url_filter": base_url_filter,
                "limit": limit,
            }
        )
        return LinkExtractionResult(source_url=url, final_url=url, links=[], total=0)

    import souwen.web.links as links_mod

    monkeypatch.setattr(links_mod, "extract_links", _fake_extract_links)
    return calls


@pytest.fixture()
def stub_sitemap_tools(monkeypatch):
    """桩掉 sitemap 下游，避免 route 测试触网。"""
    from souwen.web.sitemap import SitemapResult

    calls: list[dict] = []

    async def _fake_parse_sitemap(url, max_entries=1000):
        calls.append({"tool": "parse", "url": url, "max_entries": max_entries})
        return SitemapResult(root_url=url, entries=[], total=0, sitemaps_parsed=1)

    async def _fake_discover_sitemap(url, max_entries=1000):
        calls.append({"tool": "discover", "url": url, "max_entries": max_entries})
        return SitemapResult(root_url=url, entries=[], total=0, sitemaps_parsed=1)

    import souwen.web.sitemap as sitemap_mod

    monkeypatch.setattr(sitemap_mod, "parse_sitemap", _fake_parse_sitemap)
    monkeypatch.setattr(sitemap_mod, "discover_sitemap", _fake_discover_sitemap)
    return calls


class TestFetchEndpoint:
    """``POST /api/v1/fetch`` 端到端契约。"""

    def test_valid_request_returns_200(self, client, stub_fetch):
        """合法请求体应返回 200，并透传 stub 的聚合数据。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com/a"],
                "provider": "builtin",
                "timeout": 10,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["total_ok"] == 1
        assert body["provider"] == "builtin"
        assert body["providers"] == ["builtin"]
        assert body["strategy"] == "fallback"
        assert body["results"][0]["url"] == "https://example.com/a"
        assert stub_fetch and stub_fetch[0]["timeout"] == 10

    def test_arxiv_fulltext_provider_is_accepted(self, client, stub_fetch, monkeypatch):
        """full edition 中新 provider 应通过路由白名单校验并透传到底层 fetch。"""
        from souwen.config import get_config

        monkeypatch.setenv("SOUWEN_EDITION", "full")
        get_config.cache_clear()
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://arxiv.org/abs/2301.00001"],
                "provider": "arxiv_fulltext",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["provider"] == "arxiv_fulltext"
        assert stub_fetch and stub_fetch[0]["providers"] == ["arxiv_fulltext"]

    def test_full_fetch_provider_returns_403_in_default_pro_edition(self, client, stub_fetch):
        """已知但当前 edition 不允许的 provider 应返回 403。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://arxiv.org/abs/2301.00001"],
                "provider": "arxiv_fulltext",
            },
        )

        assert resp.status_code == 403
        assert "requires edition=full" in resp.json().get("detail", "")
        assert stub_fetch == []

    def test_multiple_providers_fanout_are_accepted(self, client, stub_fetch):
        """providers + fanout 应优先于旧版 provider 字段透传到底层 fetch。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com/a"],
                "provider": "builtin",
                "providers": ["builtin", "jina_reader"],
                "strategy": "fanout",
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["providers"] == ["builtin", "jina_reader"]
        assert body["strategy"] == "fanout"
        assert stub_fetch and stub_fetch[0]["providers"] == ["builtin", "jina_reader"]
        assert stub_fetch[0]["strategy"] == "fanout"

    def test_provider_and_url_whitespace_is_normalized(self, client, stub_fetch):
        """请求边界应先 strip provider/URL，再做 provider 白名单校验。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": [" https://example.com/a "],
                "provider": " builtin ",
            },
        )

        assert resp.status_code == 200, resp.text
        assert stub_fetch and stub_fetch[0]["urls"] == ["https://example.com/a"]
        assert stub_fetch[0]["providers"] == ["builtin"]

    def test_providers_whitespace_is_normalized(self, client, stub_fetch):
        """providers 列表项也应在路由校验前归一化。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com/a"],
                "providers": [" builtin ", " jina_reader "],
            },
        )

        assert resp.status_code == 200, resp.text
        assert stub_fetch and stub_fetch[0]["providers"] == ["builtin", "jina_reader"]

    def test_missing_urls_returns_422(self, client, stub_fetch):
        """缺少必填字段 ``urls`` 应被 Pydantic 拒绝（422）。"""
        resp = client.post("/api/v1/fetch", json={"provider": "builtin"})
        assert resp.status_code == 422

    def test_empty_urls_returns_422(self, client, stub_fetch):
        """``urls`` 至少 1 条（min_length=1），空列表应被拒绝。"""
        resp = client.post("/api/v1/fetch", json={"urls": [], "provider": "builtin"})
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "payload",
        [
            {"urls": [" "], "provider": "builtin"},
            {"urls": ["https://example.com"], "provider": " "},
            {"urls": ["https://example.com"], "providers": ["builtin", " "]},
        ],
    )
    def test_blank_url_or_provider_returns_422(self, client, stub_fetch, payload):
        """strip 后为空的 URL/provider 字段应被请求 schema 拒绝。"""
        resp = client.post("/api/v1/fetch", json=payload)

        assert resp.status_code == 422
        assert stub_fetch == []

    def test_too_many_urls_returns_422(self, client, stub_fetch):
        """``urls`` 上限 20 条（max_length=20），超出应被拒绝。"""
        urls = [f"https://example.com/{i}" for i in range(21)]
        resp = client.post("/api/v1/fetch", json={"urls": urls, "provider": "builtin"})
        assert resp.status_code == 422

    def test_invalid_provider_returns_400(self, client, stub_fetch):
        """非动态 provider 集合中的 provider 应返回 400。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com"],
                "provider": "totally-not-a-provider",
            },
        )
        assert resp.status_code == 400
        assert "无效提供者" in resp.json().get("detail", "")

    def test_invalid_provider_in_providers_returns_400(self, client, stub_fetch):
        """providers 中任一非法 provider 都应返回 400。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com"],
                "providers": ["builtin", "totally-not-a-provider"],
            },
        )
        assert resp.status_code == 400
        assert "totally-not-a-provider" in resp.json().get("detail", "")

    def test_invalid_strategy_returns_422(self, client, stub_fetch):
        """strategy 只允许 fallback / fanout。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com"],
                "providers": ["builtin", "jina_reader"],
                "strategy": "race",
            },
        )
        assert resp.status_code == 422

    def test_late_registered_provider_is_accepted(self, client, stub_fetch, monkeypatch):
        """路由应在请求时动态读取 provider，支持 reload 后新增插件。"""
        import souwen.server.routes.fetch as fetch_route

        monkeypatch.setattr(
            fetch_route,
            "fetch_providers",
            lambda: [SimpleNamespace(name="late_provider")],
        )

        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com"],
                "provider": "late_provider",
            },
        )

        assert resp.status_code == 200, resp.text
        assert stub_fetch and stub_fetch[0]["providers"] == ["late_provider"]

    def test_scrapling_route_timeout_scales_with_provider_budget(self):
        """Scrapling API 外层 timeout 应与 fetch 层批量预算一致。"""
        from souwen.server.routes.fetch import _fetch_route_timeout

        assert _fetch_route_timeout("builtin", 5, 10) == 25
        assert _fetch_route_timeout("scrapling", 5, 10) == 65
        assert _fetch_route_timeout("metaso", 5, 10) == 65
        assert _fetch_route_timeout(["builtin", "scrapling"], 5, 10, "fallback") == 85
        assert _fetch_route_timeout(["builtin", "scrapling"], 5, 10, "fanout") == 65
        assert _fetch_route_timeout(["builtin", "metaso"], 5, 10, "fallback") == 85
        assert _fetch_route_timeout(["builtin", "metaso"], 5, 10, "fanout") == 65

    def test_timeout_below_min_returns_422(self, client, stub_fetch):
        """timeout < 1 应被 Pydantic 校验拒绝（422）。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com"],
                "provider": "builtin",
                "timeout": 0.5,
            },
        )
        assert resp.status_code == 422

    def test_timeout_above_max_returns_422(self, client, stub_fetch):
        """timeout > 120 应被 Pydantic 校验拒绝（422）。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com"],
                "provider": "builtin",
                "timeout": 121,
            },
        )
        assert resp.status_code == 422

    def test_timeout_at_boundary_accepted(self, client, stub_fetch):
        """边界值 timeout=1 与 timeout=120 应被接受。"""
        for t in (1, 120):
            resp = client.post(
                "/api/v1/fetch",
                json={
                    "urls": ["https://example.com"],
                    "provider": "builtin",
                    "timeout": t,
                },
            )
            assert resp.status_code == 200, (t, resp.text)


class TestFetchToolEndpoints:
    """``GET /links`` 与 ``GET /sitemap`` 的请求边界。"""

    def test_links_blank_url_returns_422(self, client, stub_link_tools):
        """空白 URL 应在 route 层拒绝，而不是作为成功响应里的错误对象返回。"""
        resp = client.get("/api/v1/links", params={"url": "   "})

        assert resp.status_code == 422
        assert stub_link_tools == []

    def test_links_url_and_base_url_are_normalized(self, client, stub_link_tools):
        """链接提取 route 应 trim 必填 URL 与可选 base_url 过滤器。"""
        resp = client.get(
            "/api/v1/links",
            params={
                "url": " https://example.com/page ",
                "base_url": " https://example.com ",
                "limit": 5,
            },
        )

        assert resp.status_code == 200, resp.text
        assert stub_link_tools == [
            {
                "url": "https://example.com/page",
                "base_url_filter": "https://example.com",
                "limit": 5,
            }
        ]

    def test_sitemap_blank_url_returns_422(self, client, stub_sitemap_tools):
        """空白 sitemap URL 应在 route 层拒绝，避免触发下游 fetch。"""
        resp = client.get("/api/v1/sitemap", params={"url": "   "})

        assert resp.status_code == 422
        assert stub_sitemap_tools == []

    @pytest.mark.parametrize(
        ("discover", "expected_tool"),
        [(False, "parse"), (True, "discover")],
    )
    def test_sitemap_url_is_normalized(
        self,
        client,
        stub_sitemap_tools,
        discover,
        expected_tool,
    ):
        """sitemap route 应 trim URL 后再按 discover 选择下游工具。"""
        resp = client.get(
            "/api/v1/sitemap",
            params={
                "url": " https://example.com/sitemap.xml ",
                "discover": str(discover).lower(),
                "limit": 7,
            },
        )

        assert resp.status_code == 200, resp.text
        assert stub_sitemap_tools == [
            {
                "tool": expected_tool,
                "url": "https://example.com/sitemap.xml",
                "max_entries": 7,
            }
        ]
