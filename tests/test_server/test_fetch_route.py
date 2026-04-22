"""``POST /api/v1/fetch`` 路由测试。

覆盖 ``souwen.server.routes.fetch.fetch_content_endpoint`` 的请求校验
与正常路径：合法请求返回 200、必填字段缺失返回 422、provider 不在白名单
返回 400、timeout 越界由 Pydantic 校验返回 422。所有测试通过 monkeypatch
``souwen.web.fetch.fetch_content`` 桩掉真正的网络抓取。
"""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    pytest.skip("fastapi not installed", allow_module_level=True)

from souwen.models import FetchResponse, FetchResult


@pytest.fixture()
def client():
    """裸 TestClient（无密码、无鉴权）。"""
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def stub_fetch(monkeypatch):
    """把 ``souwen.web.fetch.fetch_content`` 替换为内存桩，避免网络访问。"""
    calls: list[dict] = []

    async def _fake_fetch(
        urls,
        providers=None,
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
            provider=(providers[0] if providers else "builtin"),
        )

    import souwen.web.fetch as web_fetch_mod

    monkeypatch.setattr(web_fetch_mod, "fetch_content", _fake_fetch)
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
        assert body["results"][0]["url"] == "https://example.com/a"
        assert stub_fetch and stub_fetch[0]["timeout"] == 10

    def test_arxiv_fulltext_provider_is_accepted(self, client, stub_fetch):
        """新 provider 应通过路由白名单校验并透传到底层 fetch。"""
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

    def test_missing_urls_returns_422(self, client, stub_fetch):
        """缺少必填字段 ``urls`` 应被 Pydantic 拒绝（422）。"""
        resp = client.post("/api/v1/fetch", json={"provider": "builtin"})
        assert resp.status_code == 422

    def test_empty_urls_returns_422(self, client, stub_fetch):
        """``urls`` 至少 1 条（min_length=1），空列表应被拒绝。"""
        resp = client.post(
            "/api/v1/fetch", json={"urls": [], "provider": "builtin"}
        )
        assert resp.status_code == 422

    def test_too_many_urls_returns_422(self, client, stub_fetch):
        """``urls`` 上限 20 条（max_length=20），超出应被拒绝。"""
        urls = [f"https://example.com/{i}" for i in range(21)]
        resp = client.post(
            "/api/v1/fetch", json={"urls": urls, "provider": "builtin"}
        )
        assert resp.status_code == 422

    def test_invalid_provider_returns_400(self, client, stub_fetch):
        """非 VALID_FETCH_PROVIDERS 中的 provider 应返回 400。"""
        resp = client.post(
            "/api/v1/fetch",
            json={
                "urls": ["https://example.com"],
                "provider": "totally-not-a-provider",
            },
        )
        assert resp.status_code == 400
        assert "无效提供者" in resp.json().get("detail", "")

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
