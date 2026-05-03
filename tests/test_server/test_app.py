"""SouWen Server HTTP 端点测试。

覆盖 ``souwen.server.app`` FastAPI 应用的端到端 HTTP 契约：健康检查、
管理端点鉴权、搜索端点鉴权与限流、客户端 IP 解析（XFF 可信代理）、
面板 HTML 缓存、响应 Schema、中间件（Request-ID/访问日志）、以及
生命周期日志。所有用例通过 ``fastapi.testclient.TestClient`` 同步发送
请求，对外部数据源（souwen.search / souwen.web）统一 monkeypatch。

Fixtures：
- ``client``：不设任何密码的裸客户端，搜索端点开放，管理端点默认锁定。
- ``authed_client``：预先设 ``SOUWEN_API_PASSWORD=test-secret-123``，
  用于验证旧版统一密码 Bearer Token 鉴权通路。
- ``dual_key_client``：设 visitor_password 和 admin_password 为不同值，
  验证双密钥独立认证。
"""

from types import SimpleNamespace

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not installed", allow_module_level=True)


# `_clear_config_cache` 已迁移到 tests/conftest.py 的 autouse fixture。


@pytest.fixture()
def client():
    """裸 TestClient：不设任何密码，管理端点默认锁定。"""
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def authed_client(monkeypatch):
    """带旧版统一密码认证的 TestClient。"""
    monkeypatch.setenv("SOUWEN_API_PASSWORD", "test-secret-123")
    from souwen.config import get_config

    get_config.cache_clear()
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def dual_key_client(monkeypatch):
    """双密钥独立认证 TestClient：visitor=visitor-pw, admin=admin-pw。"""
    monkeypatch.setenv("SOUWEN_VISITOR_PASSWORD", "visitor-pw")
    monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "admin-pw")
    from souwen.config import get_config

    get_config.cache_clear()
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok(self, client):
        """``GET /health`` 返回 200，且 payload 含 ``status=ok`` 与 ``version``。"""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_no_auth_required(self, authed_client):
        """即便设置了 ``api_password``，``/health`` 仍应免鉴权（K8s liveness 探针）。"""
        resp = authed_client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Admin — require_auth
# ---------------------------------------------------------------------------


class TestAdminAuth:
    # --- 无密码时默认锁定，需显式开放 ---
    def test_admin_locked_without_any_password(self, client):
        """无任何密码且未设 SOUWEN_ADMIN_OPEN 时，管理端点默认锁定。"""
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 401

    def test_admin_open_without_any_password_when_explicitly_enabled(self, client, monkeypatch):
        """SOUWEN_ADMIN_OPEN=1 时，无管理密码才显式开放管理端点。"""
        monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 200

    # --- 旧版 api_password 向后兼容 ---
    def test_admin_config_wrong_token_returns_401(self, authed_client):
        """持错误 Bearer Token 访问 ``/admin/config`` 必须返回 401。"""
        resp = authed_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_admin_config_no_token_returns_401(self, authed_client):
        """完全不带 ``Authorization`` 头访问 admin 端点，也必须 401。"""
        resp = authed_client.get("/api/v1/admin/config")
        assert resp.status_code == 401

    def test_admin_config_valid_token(self, authed_client):
        """正确 Bearer Token 可访问 ``/admin/config``；响应中 ``api_password`` 必须已脱敏为 ``***``。"""
        resp = authed_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("api_password") == "***"

    def test_admin_reload_valid_token(self, authed_client):
        """``POST /admin/config/reload`` 鉴权通过后返回 ``status=ok`` 与 ``password_set=True``。"""
        resp = authed_client.post(
            "/api/v1/admin/config/reload",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["password_set"] is True

    def test_admin_doctor_valid_token(self, authed_client):
        """``GET /admin/doctor`` 鉴权通过后返回包含 ``total``/``ok``/``sources`` 字段的连通性摘要。"""
        resp = authed_client.get(
            "/api/v1/admin/doctor",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "ok" in data
        assert "sources" in data
        first_source = data["sources"][0]
        assert "auth_requirement" in first_source
        assert "credential_fields" in first_source
        assert "risk_level" in first_source
        assert "distribution" in first_source

    def test_admin_doctor_counts_limited_and_warning_as_available(self, authed_client, monkeypatch):
        """doctor 汇总应区分严格 ok、可用、降级和失败。"""
        import souwen.doctor as doctor_mod

        monkeypatch.setattr(
            doctor_mod,
            "check_all",
            lambda: [
                {"name": "ok", "status": "ok"},
                {"name": "limited", "status": "limited"},
                {"name": "warning", "status": "warning"},
                {"name": "degraded", "status": "degraded"},
                {"name": "missing", "status": "missing_key"},
                {"name": "unavailable", "status": "unavailable"},
            ],
        )
        resp = authed_client.get(
            "/api/v1/admin/doctor",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 6
        assert data["ok"] == 1
        assert data["available"] == 4
        assert data["degraded"] == 3
        assert data["status_counts"]["degraded"] == 1
        assert data["failed"] == 2
        assert data["status_counts"]["limited"] == 1

    def test_admin_sources_config_includes_catalog_fields(self, authed_client):
        """数据源频道配置应返回 source catalog 字段，供前端展示和运维判断。"""
        resp = authed_client.get(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_requirement"] == "optional"
        assert data["key_requirement"] == "optional"
        assert data["credential_fields"] == ["openalex_email"]
        assert data["optional_credential_effect"] == "politeness"
        assert data["risk_level"] == "low"
        assert data["distribution"] == "core"

    def test_admin_ping_requires_auth(self, authed_client):
        """/admin/ping 未授权拒绝。"""
        resp = authed_client.get("/api/v1/admin/ping")
        assert resp.status_code == 401

    def test_admin_ping_authed_minimal_response(self, authed_client):
        """/admin/ping 成功响应不泄漏枚举字段。"""
        resp = authed_client.get(
            "/api/v1/admin/ping",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"status": "ok"}

    # --- 双密钥独立认证 ---
    def test_dual_key_admin_password_accepted(self, dual_key_client):
        """admin_password 可以访问管理端点。"""
        resp = dual_key_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer admin-pw"},
        )
        assert resp.status_code == 200

    def test_dual_key_visitor_password_rejected_for_admin(self, dual_key_client):
        """visitor_password 有效但权限不足，访问管理端点返回 403。"""
        resp = dual_key_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer visitor-pw"},
        )
        assert resp.status_code == 403

    def test_dual_key_no_token_rejected(self, dual_key_client):
        """admin_password 已设时，无 Token 必须 401。"""
        resp = dual_key_client.get("/api/v1/admin/config")
        assert resp.status_code == 401

    # --- admin_password 显式空字符串 → 忽略 api_password 回退，但仍需显式开放 ---
    def test_admin_explicit_empty_overrides_api_password_but_stays_locked(
        self, client, monkeypatch
    ):
        """admin_password="" 时忽略 api_password 回退，未设 SOUWEN_ADMIN_OPEN 仍锁定。"""
        monkeypatch.setenv("SOUWEN_API_PASSWORD", "legacy-pw")
        monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 401

    def test_admin_explicit_empty_can_open_with_admin_open(self, client, monkeypatch):
        """admin_password="" 且 SOUWEN_ADMIN_OPEN=1 时才开放管理端点。"""
        monkeypatch.setenv("SOUWEN_API_PASSWORD", "legacy-pw")
        monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "")
        monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 200

    # --- 仅 admin_password 时 visitor 端开放 ---
    def test_only_admin_password_leaves_search_open(self, client, monkeypatch):
        """仅设 admin_password，搜索端点应开放。"""
        monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "admin-pw")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Search auth (check_search_auth)
# ---------------------------------------------------------------------------


class TestSearchAuth:
    def test_sources_no_password_passthrough(self, client):
        """无任何密码时搜索端点可自由访问。"""
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200

    def test_sources_with_password_requires_token(self, authed_client):
        """设了 api_password 后，``/sources`` 无 Token 直接访问必须 401。"""
        resp = authed_client.get("/api/v1/sources")
        assert resp.status_code == 401

    def test_sources_with_valid_token(self, authed_client):
        """带正确 Token 访问 ``/sources`` 应 200，响应含 paper/patent/web 三类分组。"""
        resp = authed_client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "paper" in data
        assert "patent" in data
        assert "general" in data
        openalex = next(item for item in data["paper"] if item["name"] == "openalex")
        assert openalex["key_requirement"] == "optional"
        assert openalex["auth_requirement"] == "optional"
        assert openalex["credential_fields"] == ["openalex_email"]
        assert openalex["risk_level"] == "low"
        assert openalex["distribution"] == "core"

    def test_sources_omits_disabled_entries(self, client, monkeypatch):
        """sources.<name>.enabled=false 后，/sources 不应再展示该源。"""
        monkeypatch.setenv("SOUWEN_SOURCES", '{"duckduckgo": {"enabled": false}}')
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200
        data = resp.json()
        names = {item["name"] for entries in data.values() for item in entries}
        assert "duckduckgo" not in names

    def test_sources_require_multifield_secondary_credentials(self, client, monkeypatch):
        """/sources 与 admin 配置不能把仅有 primary override 的多字段源标成可用。"""
        monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
        monkeypatch.setenv("SOUWEN_EPO_CONSUMER_KEY", "")
        monkeypatch.setenv("SOUWEN_EPO_CONSUMER_SECRET", "")
        monkeypatch.setenv("SOUWEN_SOURCES", '{"epo_ops":{"api_key":"epo-key"}}')
        from souwen.config import get_config

        get_config.cache_clear()
        sources_resp = client.get("/api/v1/sources")
        assert sources_resp.status_code == 200
        patent_names = {item["name"] for item in sources_resp.json().get("patent", [])}
        assert "epo_ops" not in patent_names

        admin_resp = client.get("/api/v1/admin/sources/config/epo_ops")
        assert admin_resp.status_code == 200
        assert admin_resp.json()["has_api_key"] is False

    @pytest.mark.parametrize(
        ("source_name", "legacy_field", "client_path"),
        [
            ("searxng", "searxng_url", "souwen.web.searxng:SearXNGClient"),
            ("whoogle", "whoogle_url", "souwen.web.whoogle:WhoogleClient"),
            ("websurfx", "websurfx_url", "souwen.web.websurfx:WebsurfxClient"),
        ],
    )
    def test_sources_self_hosted_base_url_matches_clients(
        self,
        client,
        monkeypatch,
        source_name,
        legacy_field,
        client_path,
    ):
        """self_hosted 源的 base_url 判定必须和真实客户端初始化一致。"""
        import importlib

        monkeypatch.setenv(f"SOUWEN_{legacy_field.upper()}", "")
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            f'{{"{source_name}":{{"base_url":"https://{source_name}.example"}}}}',
        )
        from souwen.config import get_config

        get_config.cache_clear()
        data = client.get("/api/v1/sources").json()
        names = {item["name"] for item in data.get("general", [])}
        assert source_name in names

        module_name, class_name = client_path.split(":")
        client_cls = getattr(importlib.import_module(module_name), class_name)
        instance = client_cls()
        assert instance.instance_url == f"https://{source_name}.example"

    def test_sources_self_hosted_legacy_channel_api_key_still_works(self, client, monkeypatch):
        """旧版 sources.<name>.api_key 自建实例 URL 仍应被 catalog 与客户端接受。"""
        monkeypatch.setenv("SOUWEN_SEARXNG_URL", "")
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            '{"searxng":{"api_key":"https://legacy-searxng.example"}}',
        )
        from souwen.config import get_config

        get_config.cache_clear()
        data = client.get("/api/v1/sources").json()
        names = {item["name"] for item in data.get("general", [])}
        assert "searxng" in names

        from souwen.web.searxng import SearXNGClient

        assert SearXNGClient().instance_url == "https://legacy-searxng.example"

    def test_admin_source_config_self_hosted_legacy_channel_api_key(self, client, monkeypatch):
        """CLI/admin 共用的凭据 helper 应识别旧版 self-hosted URL 通道。"""
        monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
        monkeypatch.setenv("SOUWEN_SEARXNG_URL", "")
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            '{"searxng":{"api_key":"https://legacy-searxng.example"}}',
        )
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/admin/sources/config/searxng")
        assert resp.status_code == 200
        assert resp.json()["has_api_key"] is True

    def test_sources_uses_live_registry_for_runtime_plugins(self, client, clean_registry):
        """/sources 应从 live registry 派生，插件注销后不再返回死源。"""
        from souwen.registry.adapter import MethodSpec, SourceAdapter
        from souwen.registry.loader import lazy
        from souwen.registry.views import _reg_external, _unreg_external

        adapter = SourceAdapter(
            name="runtime_sources_probe",
            domain="fetch",
            integration="scraper",
            description="runtime source probe",
            config_field=None,
            client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
            methods={"fetch": MethodSpec("fetch")},
            needs_config=False,
        )

        assert _reg_external(adapter) is True
        data = client.get("/api/v1/sources").json()
        assert "runtime_sources_probe" in {item["name"] for item in data.get("fetch", [])}

        assert _unreg_external("runtime_sources_probe") is True
        data = client.get("/api/v1/sources").json()
        assert "runtime_sources_probe" not in {
            item["name"] for entries in data.values() for item in entries
        }

    def test_sources_keeps_runtime_web_plugin_without_internal_v0_tag(self, client, clean_registry):
        """外部 web 插件不应因缺少内部 v0_category:* tag 从 /sources 消失。"""
        from souwen.registry.adapter import MethodSpec, SourceAdapter
        from souwen.registry.loader import lazy
        from souwen.registry.views import _reg_external

        adapter = SourceAdapter(
            name="runtime_web_sources_probe",
            domain="web",
            integration="scraper",
            description="runtime web source probe",
            config_field=None,
            client_loader=lazy("souwen.web.duckduckgo:DuckDuckGoClient"),
            methods={"search": MethodSpec("search")},
            needs_config=False,
        )

        assert _reg_external(adapter) is True
        data = client.get("/api/v1/sources").json()
        names = {item["name"] for item in data.get("general", [])}
        assert "runtime_web_sources_probe" in names

    # --- 双密钥：visitor 和 admin 密码均可访问搜索端点 ---
    def test_dual_key_visitor_password_accepted(self, dual_key_client):
        """visitor_password 可以访问搜索端点。"""
        resp = dual_key_client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer visitor-pw"},
        )
        assert resp.status_code == 200

    def test_dual_key_admin_password_accepted_on_search(self, dual_key_client):
        """admin_password 也可以访问搜索端点（admin 是 visitor 超集）。"""
        resp = dual_key_client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer admin-pw"},
        )
        assert resp.status_code == 200

    def test_dual_key_wrong_token_rejected(self, dual_key_client):
        """错误 Token 被搜索端点拒绝。"""
        resp = dual_key_client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_dual_key_no_token_rejected(self, dual_key_client):
        """visitor_password 已设时，无 Token 必须 401。"""
        resp = dual_key_client.get("/api/v1/sources")
        assert resp.status_code == 401

    # --- visitor_password 显式空字符串 → 强制开放搜索 ---
    def test_visitor_explicit_empty_overrides_api_password(self, client, monkeypatch):
        """visitor_password="" 时即使 api_password 已设也强制开放搜索端点。"""
        monkeypatch.setenv("SOUWEN_API_PASSWORD", "legacy-pw")
        monkeypatch.setenv("SOUWEN_VISITOR_PASSWORD", "")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200

    # --- 仅 visitor_password 时 admin 端仍锁定 ---
    def test_only_visitor_password_leaves_admin_locked(self, client, monkeypatch):
        """仅设 visitor_password，管理端点仍需 admin 密码或 SOUWEN_ADMIN_OPEN。"""
        monkeypatch.setenv("SOUWEN_VISITOR_PASSWORD", "visitor-pw")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Three-role auth (new system)
# ---------------------------------------------------------------------------


class TestThreeRoleAuth:
    """三角色认证系统测试（Guest/User/Admin）。"""

    def test_whoami_no_password_returns_user_when_admin_locked(self, client):
        """无密码但未显式开放 admin 时，/whoami 只返回 user 权限。"""
        resp = client.get("/api/v1/whoami")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["features"]["fetch"] is False
        assert data["features"]["config_write"] is False

    def test_whoami_no_password_admin_open_returns_admin(self, client, monkeypatch):
        """SOUWEN_ADMIN_OPEN=1 时，无密码 /whoami 才返回 admin 权限。"""
        monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/whoami")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "admin"
        assert data["features"]["fetch"] is True
        assert data["features"]["config_write"] is True

    def test_whoami_admin_token(self, dual_key_client):
        """admin token 返回 admin 角色。"""
        resp = dual_key_client.get(
            "/api/v1/whoami",
            headers={"Authorization": "Bearer admin-pw"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "admin"
        assert data["features"]["fetch"] is True

    def test_whoami_user_token(self, dual_key_client):
        """visitor/user token 返回 user 角色。"""
        resp = dual_key_client.get(
            "/api/v1/whoami",
            headers={"Authorization": "Bearer visitor-pw"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["features"]["search"] is True
        assert data["features"]["fetch"] is False
        assert data["features"]["config_write"] is False

    def test_whoami_guest_enabled(self, client, monkeypatch):
        """guest_enabled=True 时无 token 返回 guest 角色。"""
        monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "admin-pw")
        monkeypatch.setenv("SOUWEN_GUEST_ENABLED", "true")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/whoami")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "guest"
        assert data["features"]["search"] is True
        assert data["features"]["fetch"] is False
        assert data["features"]["doctor"] is False

    def test_whoami_guest_disabled_no_token_401(self, dual_key_client):
        """guest_enabled=False（默认）时无 token 返回 401。"""
        resp = dual_key_client.get("/api/v1/whoami")
        assert resp.status_code == 401

    def test_role_hierarchy_admin_satisfies_user(self, dual_key_client):
        """admin token 可以访问 user 级别端点（/sources）。"""
        resp = dual_key_client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer admin-pw"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Wayback admin save route
# ---------------------------------------------------------------------------


class TestWaybackAdminSave:
    def test_public_wayback_save_route_is_not_mounted(self, authed_client):
        """写入操作不应暴露在公开 /wayback/save 路径。"""
        resp = authed_client.post(
            "/api/v1/wayback/save",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"url": "https://example.com", "timeout": 10},
        )
        assert resp.status_code == 404

    def test_admin_wayback_save_route_is_mounted(self, authed_client, monkeypatch):
        """前端应调用 /api/v1/admin/wayback/save，且管理认证后能命中路由。"""

        class FakeWaybackClient:
            async def save_page(self, url, timeout):
                return SimpleNamespace(
                    success=True,
                    snapshot_url="https://web.archive.org/web/20240101000000/https://example.com",
                    timestamp="20240101000000",
                    error=None,
                )

        monkeypatch.setattr("souwen.web.wayback.WaybackClient", FakeWaybackClient)
        resp = authed_client.post(
            "/api/v1/admin/wayback/save",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"url": "https://example.com", "timeout": 10},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_rate_limiter_import(self):
        """基础限流：同一 IP 在窗口内超过 ``max_requests`` 必须抛出异常。"""
        from souwen.server.limiter import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        limiter.check("127.0.0.1")
        limiter.check("127.0.0.1")
        limiter.check("127.0.0.1")
        with pytest.raises(Exception):
            limiter.check("127.0.0.1")

    def test_rate_limiter_different_ips(self):
        """不同 IP 的计数彼此独立，不能相互影响。"""
        from souwen.server.limiter import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        limiter.check("10.0.0.1")
        limiter.check("10.0.0.2")  # 不同 IP 不受影响

    def test_rate_limiter_rejects_invalid_params(self):
        """构造限流器时非法参数（<=0 的次数或窗口）必须直接 ``ValueError``。"""
        from souwen.server.limiter import InMemoryRateLimiter

        with pytest.raises(ValueError):
            InMemoryRateLimiter(max_requests=0, window_seconds=60)
        with pytest.raises(ValueError):
            InMemoryRateLimiter(max_requests=-1, window_seconds=60)
        with pytest.raises(ValueError):
            InMemoryRateLimiter(max_requests=10, window_seconds=0)
        with pytest.raises(ValueError):
            InMemoryRateLimiter(max_requests=10, window_seconds=-5)

    def test_rate_limiter_deque_is_bounded(self):
        """内部 ``deque`` 有 ``maxlen=2*max_requests`` 上界，防止长期运行内存泄漏。"""
        from collections import deque

        from souwen.server.limiter import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        _ = limiter._requests["1.2.3.4"]
        assert isinstance(limiter._requests["1.2.3.4"], deque)
        assert limiter._requests["1.2.3.4"].maxlen == 6


# ---------------------------------------------------------------------------
# get_client_ip — XFF 处理
# ---------------------------------------------------------------------------


def _make_request(client_host: str, headers: dict | None = None):
    """构造一个最小可用的 Starlette ``Request``，供 get_client_ip 等纯函数测试使用。"""
    from starlette.requests import Request

    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode(), v.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": (client_host, 0),
    }
    return Request(scope)


class TestClientIPResolution:
    def test_ignores_xff_without_trusted_proxies(self, monkeypatch):
        """未配置 ``SOUWEN_TRUSTED_PROXIES`` 时，XFF 头必须被忽略，仅用 socket 端 IP——防伪造。"""
        from souwen.config import get_config
        from souwen.server.limiter import get_client_ip

        monkeypatch.delenv("SOUWEN_TRUSTED_PROXIES", raising=False)
        get_config.cache_clear()
        req = _make_request("10.0.0.5", {"X-Forwarded-For": "1.2.3.4"})
        assert get_client_ip(req) == "10.0.0.5"

    def test_honors_xff_when_client_is_trusted_proxy(self, monkeypatch):
        """socket 端 IP 在可信代理 CIDR 内时，采用 XFF 链中最左侧的原始客户端 IP。"""
        from souwen.config import get_config
        from souwen.server.limiter import get_client_ip

        monkeypatch.setenv("SOUWEN_TRUSTED_PROXIES", "10.0.0.0/8")
        get_config.cache_clear()
        req = _make_request(
            "10.0.0.5",
            {"X-Forwarded-For": "203.0.113.7, 10.0.0.9"},
        )
        assert get_client_ip(req) == "203.0.113.7"

    def test_xff_ignored_when_direct_client_not_trusted(self, monkeypatch):
        """直连客户端不在可信代理集合里时，XFF 仍然必须被忽略。"""
        from souwen.config import get_config
        from souwen.server.limiter import get_client_ip

        monkeypatch.setenv("SOUWEN_TRUSTED_PROXIES", "10.0.0.0/8")
        get_config.cache_clear()
        req = _make_request("8.8.8.8", {"X-Forwarded-For": "1.2.3.4"})
        assert get_client_ip(req) == "8.8.8.8"

    def test_malformed_xff_does_not_crash(self, monkeypatch):
        """XFF 里全是非法 IP（乱码/注入）时，降级回 socket 端 IP，不得抛异常。"""
        from souwen.config import get_config
        from souwen.server.limiter import get_client_ip

        monkeypatch.setenv("SOUWEN_TRUSTED_PROXIES", "10.0.0.0/8")
        get_config.cache_clear()
        req = _make_request(
            "10.0.0.5",
            {"X-Forwarded-For": "not-an-ip, still-bad, ; DROP TABLE"},
        )
        assert get_client_ip(req) == "10.0.0.5"

    def test_malformed_xff_single_value(self, monkeypatch):
        """XFF 是单个非法值（如 XSS 载荷）时同样安全降级。"""
        from souwen.config import get_config
        from souwen.server.limiter import get_client_ip

        monkeypatch.setenv("SOUWEN_TRUSTED_PROXIES", "10.0.0.0/8")
        get_config.cache_clear()
        req = _make_request(
            "10.0.0.5",
            {"X-Forwarded-For": "<script>alert(1)</script>"},
        )
        assert get_client_ip(req) == "10.0.0.5"


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class TestPanel:
    def test_panel_endpoint(self, client):
        """``/panel`` 要么返回 HTML（200 且 content-type 含 html），要么 404（未构建面板），两种都可接受。"""
        resp = client.get("/panel")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "html" in resp.headers.get("content-type", "").lower()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_response_models_importable(self):
        """所有响应模型（Health/Search*/ConfigReload/Doctor/Sources/Error/SearchMeta）可导入并实例化。"""
        from souwen.server.schemas import (
            ErrorResponse,
            HealthResponse,
            SearchMeta,
            SearchPaperResponse,
            SearchPatentResponse,
            ConfigReloadResponse,
            DoctorResponse,
            SourcesResponse,
        )

        h = HealthResponse(status="ok", version="0.1.0")
        assert h.status == "ok"
        # 确保所有模型可实例化
        assert SearchPaperResponse(query="q", sources=[], results=[], total=0)
        assert SearchPatentResponse(query="q", sources=[], results=[], total=0)
        assert ConfigReloadResponse(status="ok", password_set=True)
        assert DoctorResponse(total=0, ok=0, sources=[])
        assert SourcesResponse()
        assert ErrorResponse(error="test", detail="msg", request_id="abc")
        assert SearchMeta(requested=["a"], succeeded=["a"], failed=[])


# ---------------------------------------------------------------------------
# Middleware — Request ID + 访问日志
# ---------------------------------------------------------------------------


class TestMiddleware:
    def test_response_has_request_id(self, client):
        """每个响应都带有非空 ``X-Request-ID`` 头，供调用方串联日志。"""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        assert len(resp.headers["x-request-id"]) > 0

    def test_response_has_response_time(self, client):
        """每个响应都带有 ``X-Response-Time`` 头，且以 ``s`` 结尾（单位秒）。"""
        resp = client.get("/health")
        assert "x-response-time" in resp.headers
        assert resp.headers["x-response-time"].endswith("s")

    def test_custom_request_id_forwarded(self, client):
        """客户端传入合法的 ``X-Request-ID`` 头时，服务端必须原样回显。"""
        resp = client.get("/health", headers={"X-Request-ID": "my-custom-id"})
        assert resp.headers["x-request-id"] == "my-custom-id"

    def test_invalid_request_id_replaced(self, client):
        """传入超长 Request-ID（>64 字符）时，服务端必须替换为自动生成的短 ID。"""
        resp = client.get(
            "/health",
            headers={"X-Request-ID": "x" * 200},
        )
        # 超长 ID 被替换为自动生成的短 ID
        assert len(resp.headers["x-request-id"]) <= 64

    def test_404_returns_error_response(self, client):
        """未知路由必须走统一错误 Schema：``error=not_found`` + 含 ``request_id``。"""
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "request_id" in data

    def test_422_validation_error(self, client):
        """参数越界（``per_page=999``）触发 422，且响应 ``error=validation_error``。"""
        # per_page 超出范围触发验证错误
        resp = client.get("/api/v1/search/paper?q=test&per_page=999")
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"] == "validation_error"
        assert "request_id" in data


# ---------------------------------------------------------------------------
# v0.6.1 第二轮评审修复
# ---------------------------------------------------------------------------


class TestQueryLengthValidation:
    """API-Q-LEN: q 参数长度校验"""

    def test_empty_q_rejected_paper(self, client):
        """paper 搜索：空 ``q`` 必须被 422 拒绝。"""
        resp = client.get("/api/v1/search/paper?q=")
        assert resp.status_code == 422

    def test_empty_q_rejected_patent(self, client):
        """patent 搜索：空 ``q`` 必须被 422 拒绝。"""
        resp = client.get("/api/v1/search/patent?q=")
        assert resp.status_code == 422

    def test_empty_q_rejected_web(self, client):
        """web 搜索：空 ``q`` 必须被 422 拒绝。"""
        resp = client.get("/api/v1/search/web?q=")
        assert resp.status_code == 422

    def test_overlong_q_rejected(self, client):
        """超长 ``q``（>500 字符）必须被 422 拒绝，防 DoS。"""
        long_q = "x" * 501
        resp = client.get(f"/api/v1/search/paper?q={long_q}")
        assert resp.status_code == 422


class TestStatusToCodeMap:
    """API-ERRMAP: 状态码 → error code 映射"""

    def test_all_expected_codes(self):
        """``_status_to_code`` 对 400/401/403/404/422/429/500/502/503/504 有明确字符串映射；未识别码（418）降级为 ``error``。"""
        from souwen.server.app import _status_to_code

        assert _status_to_code(400) == "bad_request"
        assert _status_to_code(401) == "unauthorized"
        assert _status_to_code(403) == "forbidden"
        assert _status_to_code(404) == "not_found"
        assert _status_to_code(422) == "validation_error"
        assert _status_to_code(429) == "rate_limited"
        assert _status_to_code(500) == "internal_error"
        assert _status_to_code(502) == "bad_gateway"
        assert _status_to_code(503) == "service_unavailable"
        assert _status_to_code(504) == "gateway_timeout"
        assert _status_to_code(418) == "error"


class TestSearchWebResponseShape:
    """API-WEB-RESP: /search/web 含 meta.requested/succeeded/failed"""

    def test_web_response_has_meta(self, client, monkeypatch):
        """``/search/web`` 响应必须含 ``meta.requested/succeeded/failed``，并反映每个 engine 的真实命中/失败情况。"""
        from souwen.models import SourceType, WebSearchResult
        from souwen.web import search as web_search_mod

        async def fake_web_search(q, engines=None, max_results_per_engine=10, **kw):
            return web_search_mod.WebSearchResponse(
                query=q,
                source=SourceType.WEB_DUCKDUCKGO,
                results=[
                    WebSearchResult(
                        source=SourceType.WEB_DUCKDUCKGO,
                        title="t",
                        url="https://example.com",
                        engine="duckduckgo",
                    )
                ],
            )

        monkeypatch.setattr(web_search_mod, "web_search", fake_web_search)
        resp = client.get("/api/v1/search/web?q=foo&engines=duckduckgo,bing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "foo"
        assert data["engines"] == ["duckduckgo", "bing"]
        assert "meta" in data
        assert data["meta"]["requested"] == ["duckduckgo", "bing"]
        assert "duckduckgo" in data["meta"]["succeeded"]
        assert "bing" in data["meta"]["failed"]
        assert data["total"] == 1


class TestSearchPaperDefaults:
    """API-PAPER-DEFAULTS: /search/paper 默认源与 registry 保持一致"""

    def test_paper_defaults_come_from_registry(self, client, monkeypatch):
        """未传 ``sources`` 时，应由 ``souwen.search`` 自行应用 registry 默认源。"""
        import importlib

        from souwen.server.routes import search as routes_search

        search_mod = importlib.import_module("souwen.search")
        captured: dict = {}

        async def fake_search(q, sources=None, per_page=10, **kw):
            captured["sources"] = sources
            return []

        monkeypatch.setattr(search_mod, "search_papers", fake_search)
        resp = client.get("/api/v1/search/paper?q=foo")
        assert resp.status_code == 200
        data = resp.json()
        assert captured["sources"] is None
        assert data["sources"] == routes_search._DEFAULT_PAPER_SOURCES
        assert data["meta"]["requested"] == routes_search._DEFAULT_PAPER_SOURCES
        assert data["meta"]["failed"] == routes_search._DEFAULT_PAPER_SOURCES


class TestPerPageAlias:
    """API-PAGE-NAME: /search/web 支持 per_page + max_results"""

    def _patch(self, monkeypatch):
        captured: dict = {}
        from souwen.models import SourceType
        from souwen.web import search as web_search_mod

        async def fake_web_search(q, engines=None, max_results_per_engine=10, **kw):
            captured["max"] = max_results_per_engine
            return web_search_mod.WebSearchResponse(
                query=q, source=SourceType.WEB_DUCKDUCKGO, results=[]
            )

        monkeypatch.setattr(web_search_mod, "web_search", fake_web_search)
        return captured

    def test_per_page_accepted(self, client, monkeypatch):
        """``/search/web?per_page=N`` 必须映射到底层 ``max_results_per_engine=N``。"""
        captured = self._patch(monkeypatch)
        resp = client.get("/api/v1/search/web?q=foo&per_page=5")
        assert resp.status_code == 200
        assert captured["max"] == 5

    def test_max_results_accepted_for_backcompat(self, client, monkeypatch):
        """保留历史别名 ``max_results=N``，行为等同 ``per_page``（向后兼容契约）。"""
        captured = self._patch(monkeypatch)
        resp = client.get("/api/v1/search/web?q=foo&max_results=7")
        assert resp.status_code == 200
        assert captured["max"] == 7


class TestRateLimitHeaders:
    """API-RLHEAD: 429 响应包含 X-RateLimit-* 头"""

    def test_429_has_ratelimit_headers(self, client, monkeypatch):
        """触发限流时响应必须携带 ``X-RateLimit-Limit/Remaining/Reset`` 三个头，且 body 为 ``error=rate_limited``。"""
        import sys

        from souwen.server import limiter as limiter_mod

        small = limiter_mod.InMemoryRateLimiter(max_requests=2, window_seconds=60)
        monkeypatch.setattr(limiter_mod, "_search_limiter", small)

        async def fake_search(q, sources=None, per_page=10, **kw):
            return []

        search_mod = sys.modules["souwen.search"]
        monkeypatch.setattr(search_mod, "search_papers", fake_search)

        r1 = client.get("/api/v1/search/paper?q=a")
        r2 = client.get("/api/v1/search/paper?q=a")
        r3 = client.get("/api/v1/search/paper?q=a")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429
        assert r3.headers.get("x-ratelimit-limit") == "2"
        assert r3.headers.get("x-ratelimit-remaining") == "0"
        reset = r3.headers.get("x-ratelimit-reset")
        assert reset is not None and reset.isdigit()
        assert r3.json()["error"] == "rate_limited"


class TestReadiness:
    """API-READY: /readiness 端点"""

    def test_readiness_ok(self, client):
        """``/readiness`` 200 + ``ready=True`` + 非空 ``version``。"""
        resp = client.get("/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True
        assert data["version"]

    def test_readiness_no_auth_required(self, authed_client):
        """``/readiness`` 即使配置了密码也免鉴权（K8s readiness probe 无法携带 Token）。"""
        # 有密码时仍应放行（K8s probe 无 Authorization 头）
        resp = authed_client.get("/readiness")
        assert resp.status_code == 200


class TestPanelEtag:
    """API-PANEL-CACHE: panel.html ETag + Cache-Control"""

    def test_panel_returns_etag(self, client):
        """``/panel`` 响应带引号包裹的 ``ETag`` + ``Cache-Control: max-age=...``；再带 ``If-None-Match`` 请求必须 304 + 空 body。"""
        # 清空缓存，确保重新计算
        from souwen.server import app as app_mod

        app_mod._panel_cache = None
        app_mod._panel_etag = None

        resp = client.get("/panel")
        if resp.status_code == 404:
            pytest.skip("panel.html not available")
        assert resp.status_code == 200
        etag = resp.headers.get("etag")
        assert etag and etag.startswith('"') and etag.endswith('"')
        assert "max-age" in resp.headers.get("cache-control", "")

        resp2 = client.get("/panel", headers={"If-None-Match": etag})
        assert resp2.status_code == 304
        assert resp2.content == b""

    def test_root_redirects_or_returns_api_info(self, client):
        """根路径 ``/`` 重定向到 /docs 或返回 API 信息 JSON。"""
        resp = client.get("/", follow_redirects=False)
        if resp.status_code == 302:
            assert "/docs" in resp.headers.get("location", "")
        else:
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "SouWen API"
            assert "panel" in data


class TestSearchTimeout:
    """API-TIMEOUT: 搜索端点 timeout 参数返回 504"""

    def test_paper_timeout_returns_504(self, client, monkeypatch):
        """paper 搜索 timeout 到期 → 504 ``gateway_timeout``（底层协程被挂起 5s，timeout=1）。"""
        import asyncio as _asyncio
        import sys

        async def slow(*a, **kw):
            await _asyncio.sleep(5)
            return []

        search_mod = sys.modules["souwen.search"]
        monkeypatch.setattr(search_mod, "search_papers", slow)
        resp = client.get("/api/v1/search/paper?q=foo&timeout=1")
        assert resp.status_code == 504
        assert resp.json()["error"] == "gateway_timeout"

    def test_patent_timeout_returns_504(self, client, monkeypatch):
        """patent 搜索 timeout 到期 → 504 ``gateway_timeout``。"""
        import asyncio as _asyncio
        import sys

        async def slow(*a, **kw):
            await _asyncio.sleep(5)
            return []

        search_mod = sys.modules["souwen.search"]
        monkeypatch.setattr(search_mod, "search_patents", slow)
        resp = client.get("/api/v1/search/patent?q=foo&timeout=1")
        assert resp.status_code == 504
        assert resp.json()["error"] == "gateway_timeout"

    def test_web_timeout_returns_504(self, client, monkeypatch):
        """web 搜索 timeout 到期 → 504 ``gateway_timeout``。"""
        import asyncio as _asyncio
        from souwen.web import search as web_search_mod

        async def slow(*a, **kw):
            await _asyncio.sleep(5)

        monkeypatch.setattr(web_search_mod, "web_search", slow)
        resp = client.get("/api/v1/search/web?q=foo&timeout=1")
        assert resp.status_code == 504
        assert resp.json()["error"] == "gateway_timeout"


class TestLifecycleLogging:
    """WARP-LIFECYCLE: 启动/关停日志"""

    def test_startup_logs_warp_state(self, monkeypatch):
        """应用启动/关停日志必须打印 ``WARP state:``（含配置摘要）与 ``shutting down``（关停标记），便于运维定位生命周期问题。"""
        import logging as _logging

        from fastapi.testclient import TestClient

        from souwen.server.app import app

        captured: list[str] = []

        class _H(_logging.Handler):
            def emit(self, record):
                captured.append(record.getMessage())

        server_logger = _logging.getLogger("souwen.server")
        prev_level = server_logger.level
        server_logger.setLevel(_logging.INFO)
        h = _H(level=_logging.INFO)
        server_logger.addHandler(h)
        try:
            with TestClient(app) as c:
                c.get("/health")
        finally:
            server_logger.removeHandler(h)
            server_logger.setLevel(prev_level)
        joined = " || ".join(captured)
        assert "WARP state:" in joined, f"captured={captured!r}"
        assert "shutting down" in joined
