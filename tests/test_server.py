"""SouWen Server HTTP 端点测试"""

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not installed", allow_module_level=True)


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """每个测试前清除配置缓存，避免状态泄漏。"""
    from souwen.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture()
def client():
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def authed_client(monkeypatch):
    """带密码认证的 TestClient。"""
    monkeypatch.setenv("SOUWEN_API_PASSWORD", "test-secret-123")
    from souwen.config import get_config

    get_config.cache_clear()
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_no_auth_required(self, authed_client):
        resp = authed_client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Admin — require_auth
# ---------------------------------------------------------------------------


class TestAdminAuth:
    def test_admin_config_no_password_set_allows_access(self, client):
        """api_password 未设置时，管理端点允许免密码访问。"""
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 200

    def test_admin_config_wrong_token_returns_401(self, authed_client):
        resp = authed_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_admin_config_no_token_returns_401(self, authed_client):
        resp = authed_client.get("/api/v1/admin/config")
        # 无 token → HTTPBearer auto_error=False → credentials=None → 401
        assert resp.status_code == 401

    def test_admin_config_valid_token(self, authed_client):
        resp = authed_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # 密码字段已脱敏
        assert data.get("api_password") == "***"

    def test_admin_reload_valid_token(self, authed_client):
        resp = authed_client.post(
            "/api/v1/admin/config/reload",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["password_set"] is True

    def test_admin_doctor_valid_token(self, authed_client):
        resp = authed_client.get(
            "/api/v1/admin/doctor",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "ok" in data
        assert "sources" in data


# ---------------------------------------------------------------------------
# Search auth (check_search_auth)
# ---------------------------------------------------------------------------


class TestSearchAuth:
    def test_sources_no_password_passthrough(self, client):
        """api_password 未设置时搜索端点可自由访问。"""
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200

    def test_sources_with_password_requires_token(self, authed_client):
        resp = authed_client.get("/api/v1/sources")
        assert resp.status_code == 401

    def test_sources_with_valid_token(self, authed_client):
        resp = authed_client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "paper" in data
        assert "patent" in data
        assert "web" in data


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_rate_limiter_import(self):
        from souwen.server.limiter import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        limiter.check("127.0.0.1")
        limiter.check("127.0.0.1")
        limiter.check("127.0.0.1")
        with pytest.raises(Exception):
            limiter.check("127.0.0.1")

    def test_rate_limiter_different_ips(self):
        from souwen.server.limiter import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        limiter.check("10.0.0.1")
        limiter.check("10.0.0.2")  # 不同 IP 不受影响


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class TestPanel:
    def test_panel_endpoint(self, client):
        resp = client.get("/panel")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "html" in resp.headers.get("content-type", "").lower()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_response_models_importable(self):
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
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        assert len(resp.headers["x-request-id"]) > 0

    def test_response_has_response_time(self, client):
        resp = client.get("/health")
        assert "x-response-time" in resp.headers
        assert resp.headers["x-response-time"].endswith("s")

    def test_custom_request_id_forwarded(self, client):
        resp = client.get("/health", headers={"X-Request-ID": "my-custom-id"})
        assert resp.headers["x-request-id"] == "my-custom-id"

    def test_invalid_request_id_replaced(self, client):
        resp = client.get(
            "/health",
            headers={"X-Request-ID": "x" * 200},
        )
        # 超长 ID 被替换为自动生成的短 ID
        assert len(resp.headers["x-request-id"]) <= 64

    def test_404_returns_error_response(self, client):
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "request_id" in data

    def test_422_validation_error(self, client):
        # per_page 超出范围触发验证错误
        resp = client.get("/api/v1/search/paper?q=test&per_page=999")
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"] == "validation_error"
        assert "request_id" in data
