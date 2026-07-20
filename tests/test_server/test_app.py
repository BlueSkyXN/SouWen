"""SouWen Server HTTP 端点测试。

覆盖 ``souwen.server.app`` FastAPI 应用的端到端 HTTP 契约：健康检查、
管理端点鉴权、搜索端点鉴权与限流、客户端 IP 解析（XFF 可信代理）、
面板 HTML 缓存、响应 Schema、中间件（Request-ID/访问日志）、以及
生命周期日志。所有用例通过 ``fastapi.testclient.TestClient`` 同步发送
请求，对外部数据源（souwen.search / souwen.web）统一 monkeypatch。

Fixtures：
- ``client``：不设任何密码的裸客户端，搜索端点开放，管理端点默认锁定。
- ``authed_client``：预先设同值 ``SOUWEN_USER_PASSWORD`` 和
  ``SOUWEN_ADMIN_PASSWORD``，用于验证 Bearer Token 鉴权通路。
- ``dual_key_client``：设 user_password 和 admin_password 为不同值，
  验证双密钥独立认证。
"""

from types import SimpleNamespace

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not installed", allow_module_level=True)


# `_clear_config_cache` 已迁移到 tests/conftest.py 的 autouse fixture。


@pytest.fixture(autouse=True)
def _isolate_config_files(monkeypatch, tmp_path):
    """Server 端点测试固定使用空 HOME/cwd，避免开发机真实配置影响鉴权状态。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
    for key in (
        "SOUWEN_API_PASSWORD",
        "SOUWEN_VISITOR_PASSWORD",
        "SOUWEN_USER_PASSWORD",
        "SOUWEN_ADMIN_PASSWORD",
        "SOUWEN_ADMIN_OPEN",
        "SOUWEN_GUEST_ENABLED",
        "SOUWEN_SOURCES",
        "SOUWEN_TRUSTED_PROXIES",
        "SOUWEN_EDITION",
    ):
        monkeypatch.delenv(key, raising=False)
    from souwen.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture()
def client():
    """裸 TestClient：不设任何密码，管理端点默认锁定。"""
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def authed_client(monkeypatch):
    """带用户/管理同密认证的 TestClient。"""
    monkeypatch.setenv("SOUWEN_USER_PASSWORD", "test-secret-123")
    monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "test-secret-123")
    from souwen.config import get_config

    get_config.cache_clear()
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def dual_key_client(monkeypatch):
    """双密钥独立认证 TestClient：user=user-pw, admin=admin-pw。"""
    monkeypatch.setenv("SOUWEN_USER_PASSWORD", "user-pw")
    monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "admin-pw")
    from souwen.config import get_config

    get_config.cache_clear()
    from souwen.server.app import app

    return TestClient(app, raise_server_exceptions=False)


def _sources_by_name(payload: dict) -> dict[str, dict]:
    return {item["name"]: item for item in payload["sources"]}


def _doctor_source(name: str, status: str, **overrides) -> dict:
    """Build a doctor source payload matching the public response contract."""

    return {
        "name": name,
        "category": "paper",
        "status": status,
        "integration_type": "open_api",
        "required_key": None,
        "key_requirement": "none",
        "auth_requirement": "none",
        "credential_fields": [],
        "optional_credential_effect": None,
        "risk_level": "low",
        "risk_reasons": [],
        "distribution": "core",
        "package_extra": None,
        "stability": "stable",
        "usage_note": None,
        "min_edition": "basic",
        "edition": "pro",
        "edition_available": True,
        "edition_reason": "",
        "runtime_available": True,
        "runtime_reason": "",
        "credentials_satisfied": True,
        "config_available": True,
        "config_reason": "",
        "available": status in {"ok", "limited", "warning", "degraded"},
        "message": status,
        "enabled": True,
        "description": f"{name} test source",
        "channel": None,
        **overrides,
    }


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
        assert "source_sha" in data

    def test_health_reports_validated_source_sha(self, client, monkeypatch):
        monkeypatch.setenv("SOUWEN_SOURCE_SHA", "d" * 40)

        data = client.get("/health").json()

        assert data["source_sha"] == "d" * 40

    def test_health_no_auth_required(self, authed_client):
        """即便设置了认证密码，``/health`` 仍应免鉴权（K8s liveness 探针）。"""
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

    # --- 管理密码认证 ---
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
        """正确 Bearer Token 可访问 ``/admin/config``；密码字段必须已脱敏。"""
        resp = authed_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "api_password" not in data
        assert "visitor_password" not in data
        assert data.get("user_password") == "***"
        assert data.get("admin_password") == "***"

    def test_proxy_and_application_auth_headers_remain_independent(self, dual_key_client):
        """上游占用 Authorization 时，应用层 token 仍能独立完成 admin 鉴权。"""
        resp = dual_key_client.get(
            "/api/v1/whoami",
            headers={
                "Authorization": "Bearer hf-private-space-read-token",
                "X-SouWen-Token": "admin-pw",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_invalid_explicit_application_token_does_not_fall_back(self, dual_key_client):
        """显式 X-SouWen-Token 无效时，不得回退到另一个 header。"""
        resp = dual_key_client.get(
            "/api/v1/whoami",
            headers={
                "Authorization": "Bearer admin-pw",
                "X-SouWen-Token": "wrong-app-token",
            },
        )

        assert resp.status_code == 401

    def test_admin_config_redacts_nested_secret_fields(self, authed_client, monkeypatch):
        """``/admin/config`` 的嵌套配置同样不能泄漏 channel 或 LLM 凭据。"""
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            (
                '{"openalex": {'
                '"api_key": "source-secret", '
                '"proxy": "http://user:source-proxy-pass@proxy.example:8080?token=source-proxy-token", '
                '"base_url": "https://source.example/search?apiKey=source-base-key&safe=1", '
                '"headers": {'
                '"Authorization": "Bearer header-secret", '
                '"X-ApiKey": "header-api-key-secret", '
                '"X-Session-Id": "header-session-secret", '
                '"X-JWT": "header-jwt-secret", '
                '"X-Trace-Id": "trace-1"'
                "}, "
                '"params": {'
                '"api_key": "param-secret", '
                '"apiKey": "camel-api-key-secret", '
                '"accessToken": "camel-access-value", '
                '"clientSecret": "camel-client-secret", '
                '"apikey": "compact-api-key-secret", '
                '"session_id": "param-session-secret", '
                '"sid": "param-sid-secret", '
                '"jwt": "param-jwt-secret", '
                '"csrftoken": "param-csrf-secret", '
                '"page": 1'
                "}"
                "}}"
            ),
        )
        monkeypatch.setenv(
            "SOUWEN_LLM",
            (
                '{"enabled": true, '
                '"api_key": "llm-secret", '
                '"api_keys": ["llm-secret-1", "llm-secret-2"], '
                '"base_url": "https://llm.example"}'
            ),
        )
        monkeypatch.setenv(
            "SOUWEN_PROXY",
            "socks5://user:global-proxy-pass@proxy.example:1080?token=global-proxy-token&safe=1",
        )
        monkeypatch.setenv(
            "SOUWEN_PROXY_POOL",
            ",".join(
                [
                    "http://user:pool-pass@pool.example:8080?apiKey=pool-api-key&safe=1",
                    "http://plain.example:8080",
                ]
            ),
        )
        from souwen.config import get_config

        get_config.cache_clear()
        resp = authed_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        openalex = data["sources"]["openalex"]
        assert openalex["api_key"] == "***"
        assert "source-proxy-pass" not in resp.text
        assert "source-proxy-token" not in resp.text
        assert "source-base-key" not in resp.text
        assert openalex["proxy"] == "http://***@proxy.example:8080?token=***"
        assert openalex["base_url"] == "https://source.example/search?apiKey=***&safe=1"
        assert openalex["headers"]["Authorization"] == "***"
        assert openalex["headers"]["X-ApiKey"] == "***"
        assert openalex["headers"]["X-Session-Id"] == "***"
        assert openalex["headers"]["X-JWT"] == "***"
        assert openalex["headers"]["X-Trace-Id"] == "trace-1"
        assert openalex["params"]["api_key"] == "***"
        assert openalex["params"]["apiKey"] == "***"
        assert openalex["params"]["accessToken"] == "***"
        assert openalex["params"]["clientSecret"] == "***"
        assert openalex["params"]["apikey"] == "***"
        assert openalex["params"]["session_id"] == "***"
        assert openalex["params"]["sid"] == "***"
        assert openalex["params"]["jwt"] == "***"
        assert openalex["params"]["csrftoken"] == "***"
        assert openalex["params"]["page"] == 1

        assert data["llm"]["api_key"] == "***"
        assert data["llm"]["api_keys"] == "***"
        assert data["llm"]["base_url"] == "https://llm.example"
        assert "global-proxy-pass" not in resp.text
        assert "global-proxy-token" not in resp.text
        assert "pool-pass" not in resp.text
        assert "pool-api-key" not in resp.text
        assert data["proxy"] == "socks5://***@proxy.example:1080?token=***&safe=1"
        assert data["proxy_pool"][0] == "http://***@pool.example:8080?apiKey=***&safe=1"
        assert data["proxy_pool"][1] == "http://plain.example:8080"

    def test_admin_http_backend_get_valid_token(self, authed_client):
        """``GET /admin/http-backend`` 应返回当前后端快照，供 CD smoke 安全恢复状态。"""
        resp = authed_client.get(
            "/api/v1/admin/http-backend",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default"] in {"auto", "curl_cffi", "httpx"}
        assert isinstance(data["overrides"], dict)
        assert isinstance(data["curl_cffi_available"], bool)

    def test_admin_http_backend_update_trims_default(self, authed_client):
        """默认 HTTP backend 更新应先 trim，再做允许值校验。"""
        resp = authed_client.put(
            "/api/v1/admin/http-backend",
            headers={"Authorization": "Bearer test-secret-123"},
            params={"default": " httpx "},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["default"] == "httpx"

    def test_admin_http_backend_update_trims_source_override(self, authed_client):
        """按源覆盖应先 trim source/backend，再校验源名和后端值。"""
        resp = authed_client.put(
            "/api/v1/admin/http-backend",
            headers={"Authorization": "Bearer test-secret-123"},
            params={"source": " duckduckgo ", "backend": " httpx "},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["overrides"]["duckduckgo"] == "httpx"

    def test_admin_http_backend_source_backend_must_be_paired(self, authed_client):
        """只传 source 或只传 backend 不应返回成功 no-op。"""
        for params in ({"source": "duckduckgo"}, {"backend": "httpx"}):
            resp = authed_client.put(
                "/api/v1/admin/http-backend",
                headers={"Authorization": "Bearer test-secret-123"},
                params=params,
            )

            assert resp.status_code == 400
            assert "source 和 backend 必须同时提供" in resp.json()["detail"]

    def test_admin_proxy_update_trims_proxy_url(self, authed_client):
        """全局 proxy 应保存校验后的规范 URL，而不是请求体原始字符串。"""
        resp = authed_client.put(
            "/api/v1/admin/proxy",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"proxy": " http://proxy.example:8080 "},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["proxy"] == "http://proxy.example:8080"

    def test_admin_proxy_response_redacts_url_secrets_but_keeps_runtime_value(
        self,
        authed_client,
        monkeypatch,
    ):
        """全局代理读写响应不应泄漏凭据，但运行时配置仍应保留真实 URL。"""
        proxy = "socks5://user:proxy-pass@proxy.example:1080?token=proxy-token&safe=1"
        pool = "http://user:pool-pass@pool.example:8080?apiKey=pool-key&safe=1"
        monkeypatch.setenv("SOUWEN_PROXY", proxy)
        monkeypatch.setenv("SOUWEN_PROXY_POOL", pool)
        from souwen.config import get_config

        get_config.cache_clear()
        get_resp = authed_client.get(
            "/api/v1/admin/proxy",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert get_resp.status_code == 200, get_resp.text
        assert "proxy-pass" not in get_resp.text
        assert "proxy-token" not in get_resp.text
        assert "pool-pass" not in get_resp.text
        assert "pool-key" not in get_resp.text
        assert get_resp.json()["proxy"] == "socks5://***@proxy.example:1080?token=***&safe=1"
        assert get_resp.json()["proxy_pool"] == ["http://***@pool.example:8080?apiKey=***&safe=1"]

        put_resp = authed_client.put(
            "/api/v1/admin/proxy",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"proxy": proxy, "proxy_pool": [pool]},
        )
        assert put_resp.status_code == 200, put_resp.text
        assert "proxy-pass" not in put_resp.text
        assert "pool-pass" not in put_resp.text
        assert put_resp.json()["proxy"] == "socks5://***@proxy.example:1080?token=***&safe=1"
        assert get_config().proxy == proxy
        assert get_config().proxy_pool == [pool]

    def test_admin_proxy_rejects_redacted_placeholder(self, authed_client):
        """脱敏后的代理占位符不能被提交保存，避免覆盖真实配置。"""
        resp = authed_client.put(
            "/api/v1/admin/proxy",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"proxy": "socks5://***@proxy.example:1080?token=***"},
        )

        assert resp.status_code == 422
        assert "脱敏显示值" in resp.json()["detail"]

    def test_admin_proxy_update_blank_proxy_clears_config(self, authed_client):
        """空白 proxy 应视为清空配置，不能把空白字符串写入运行时配置。"""
        resp = authed_client.put(
            "/api/v1/admin/proxy",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"proxy": "   "},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["proxy"] is None

    def test_admin_proxy_pool_rejects_blank_entry(self, authed_client):
        """proxy_pool 中的空白条目应失败，避免无效输入被静默丢弃。"""
        resp = authed_client.put(
            "/api/v1/admin/proxy",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"proxy_pool": [" http://proxy.example:8080 ", "   "]},
        )

        assert resp.status_code == 422
        assert "proxy_pool[1] 不能是空字符串" in resp.json()["detail"]
        from souwen.config import get_config

        assert get_config().proxy_pool == []

    def test_admin_proxy_error_redacts_url_secrets(self, authed_client):
        """全局 proxy 校验错误不应回显 URL userinfo 或敏感 query。"""
        resp = authed_client.put(
            "/api/v1/admin/proxy",
            headers={"Authorization": "Bearer test-secret-123"},
            json={
                "proxy": "ftp://user:pass@proxy.example:21?token=proxy-secret&safe=1",
            },
        )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "user:pass" not in detail
        assert "proxy-secret" not in detail
        assert "ftp://***@proxy.example:21?token=***&safe=1" in detail

    def test_admin_proxy_pool_error_redacts_url_secrets(self, authed_client):
        """proxy_pool 校验错误不应回显 URL userinfo 或敏感 query。"""
        resp = authed_client.put(
            "/api/v1/admin/proxy",
            headers={"Authorization": "Bearer test-secret-123"},
            json={
                "proxy_pool": [
                    "http://ok.example:8080",
                    "ftp://user:pass@proxy.example:21?token=pool-secret&safe=1",
                ],
            },
        )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "user:pass" not in detail
        assert "pool-secret" not in detail
        assert "ftp://***@proxy.example:21?token=***&safe=1" in detail

    def test_admin_reload_valid_token(self, authed_client):
        """``POST /admin/config/reload`` 鉴权通过后返回 ``status=ok`` 与 ``password_set=True``。"""
        resp = authed_client.post(
            "/api/v1/admin/config/reload",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["password_set"] is True

    def test_admin_config_yaml_validation_error_does_not_echo_input_secret(self, authed_client):
        """YAML dry-run 校验失败不应把 Pydantic input_value 中的 secret 回显给客户端。"""
        resp = authed_client.put(
            "/api/v1/admin/config/yaml",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"content": "sources:\n  openalex: token-secret\n"},
        )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "token-secret" not in detail
        assert "input_value" not in detail
        assert "sources.openalex" in detail

    def test_admin_config_yaml_uses_current_home_at_request_time(
        self,
        authed_client,
        monkeypatch,
        tmp_path,
    ):
        """YAML 配置路径应按请求时的 HOME 解析，不能绑定模块导入时的 HOME。"""
        import importlib

        import souwen.server.routes.admin.config as config_route

        stale_home = tmp_path / "stale-home"
        current_home = tmp_path / "current-home"
        stale_config = stale_home / ".config" / "souwen" / "config.yaml"
        current_config = current_home / ".config" / "souwen" / "config.yaml"
        stale_config.parent.mkdir(parents=True)
        current_config.parent.mkdir(parents=True)
        stale_config.write_text("server:\n  host: stale-home\n", encoding="utf-8")
        current_config.write_text("server:\n  host: current-home\n", encoding="utf-8")

        monkeypatch.setenv("HOME", str(stale_home))
        monkeypatch.setenv("USERPROFILE", str(stale_home))
        importlib.reload(config_route)

        monkeypatch.setenv("HOME", str(current_home))
        monkeypatch.setenv("USERPROFILE", str(current_home))
        from souwen.config import get_config

        get_config.cache_clear()
        resp = authed_client.get(
            "/api/v1/admin/config/yaml",
            headers={"Authorization": "Bearer test-secret-123"},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["path"] == str(current_config)
        assert "current-home" in data["content"]
        assert "stale-home" not in data["content"]

    def test_admin_config_yaml_reload_error_redacts_secret_detail(
        self,
        authed_client,
        monkeypatch,
        tmp_path,
    ):
        """YAML 保存后的 reload 失败响应不应泄漏底层异常中的 secret。"""
        import souwen.config as config_mod

        secret_error = (
            "reload failed token=reload-secret "
            "Cookie: sid=session-secret "
            "callback https://auth.example/cb?apiKey=url-api-key-secret&safe=1"
        )

        def fake_reload_config():
            raise RuntimeError(secret_error)

        monkeypatch.setattr(config_mod, "reload_config", fake_reload_config)
        resp = authed_client.put(
            "/api/v1/admin/config/yaml",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"content": "server:\n  expose_docs: true\n"},
        )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "reload-secret" not in detail
        assert "session-secret" not in detail
        assert "url-api-key-secret" not in detail
        assert "token:***" in detail
        assert "Cookie:***" in detail
        assert "apiKey=***" in detail
        assert "safe=1" in detail
        assert not (tmp_path / ".config" / "souwen" / "config.yaml").exists()

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
        assert data["edition"] == "pro"
        assert "sources" in data
        first_source = data["sources"][0]
        assert "auth_requirement" in first_source
        assert "credential_fields" in first_source
        assert "risk_level" in first_source
        assert "distribution" in first_source
        assert "min_edition" in first_source
        assert "edition_available" in first_source
        assert "edition_reason" in first_source
        assert "available" in first_source

    def test_admin_doctor_marks_edition_unavailable(self, authed_client, monkeypatch):
        """doctor 应暴露当前 edition，并让 basic 下的 pro 源显示需升级。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = authed_client.get(
            "/api/v1/admin/doctor",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["edition"] == "basic"
        openalex = _sources_by_name(data)["openalex"]
        assert openalex["status"] == "unavailable"
        assert openalex["min_edition"] == "pro"
        assert openalex["edition"] == "basic"
        assert openalex["edition_available"] is False
        assert "source 'openalex' requires edition=pro" in openalex["edition_reason"]
        assert openalex["available"] is False

    def test_admin_doctor_counts_limited_and_warning_as_available(self, authed_client, monkeypatch):
        """doctor 汇总应区分严格 ok、可用、降级和失败。"""
        import souwen.doctor as doctor_mod

        monkeypatch.setattr(
            doctor_mod,
            "check_all",
            lambda: [
                _doctor_source("ok", "ok"),
                _doctor_source("limited", "limited"),
                _doctor_source("warning", "warning"),
                _doctor_source("degraded", "degraded"),
                _doctor_source("missing", "missing_key", available=False),
                _doctor_source("unavailable", "unavailable", available=False),
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
        assert data["degraded_total"] == 3
        assert data["status_counts"]["degraded"] == 1
        assert data["failed"] == 2
        assert data["status_counts"]["limited"] == 1

    def test_admin_doctor_live_probe_is_explicit(self, authed_client, monkeypatch):
        """live=true 时才应调用联网 probe，并在响应中暴露 probe 汇总。"""
        import souwen.doctor as doctor_mod

        captured: dict[str, object] = {}

        async def fake_check_all_live(sources=None, timeout=5.0):
            captured["sources"] = sources
            captured["timeout"] = timeout
            return [
                _doctor_source(
                    "openalex",
                    "ok",
                    live_probe={
                        "status": "ok",
                        "message": "live search returned 1 result(s)",
                        "elapsed_ms": 1,
                    },
                )
            ]

        monkeypatch.setattr(doctor_mod, "check_all_live", fake_check_all_live)

        resp = authed_client.get(
            "/api/v1/admin/doctor?live=true&source=openalex&timeout=1",
            headers={"Authorization": "Bearer test-secret-123"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert captured["sources"] == ["openalex"]
        assert captured["timeout"] == 1.0
        assert data["probe_mode"] == "live"
        assert data["live_probe"]["ok"] == 1
        assert data["sources"][0]["live_probe"]["status"] == "ok"

    def test_admin_doctor_keeps_runtime_web_plugin_without_explicit_category(
        self,
        authed_client,
        clean_registry,
    ):
        """admin doctor 应返回不声明 category 的外部 web 插件。"""
        from tests.test_doctor import register_runtime_web_doctor_probe

        name = register_runtime_web_doctor_probe()
        resp = authed_client.get(
            "/api/v1/admin/doctor",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        sources = {item["name"]: item for item in resp.json()["sources"]}
        assert sources[name]["category"] == "web_general"
        assert sources[name]["distribution"] == "plugin"

    def test_user_doctor_allows_user_token_without_admin_access(
        self,
        dual_key_client,
        monkeypatch,
    ):
        """``GET /doctor`` 是 User+ 读端点，不能顺带开放 admin doctor。"""
        import souwen.doctor as doctor_mod

        monkeypatch.setattr(
            doctor_mod,
            "check_all",
            lambda: [
                _doctor_source("openalex", "ok"),
                _doctor_source("semantic_scholar", "limited"),
            ],
        )

        resp = dual_key_client.get(
            "/api/v1/doctor",
            headers={"Authorization": "Bearer user-pw"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["ok"] == 1
        assert data["available"] == 2
        assert data["sources"][0]["name"] == "openalex"

        admin_resp = dual_key_client.get(
            "/api/v1/admin/doctor",
            headers={"Authorization": "Bearer user-pw"},
        )
        assert admin_resp.status_code == 403

    def test_user_doctor_requires_user_when_user_password_is_configured(self, dual_key_client):
        """配置 user_password 后，guest/无 token 不能读取 doctor 摘要。"""
        resp = dual_key_client.get("/api/v1/doctor")

        assert resp.status_code == 401

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
        assert data["min_edition"] == "pro"
        assert data["edition_available"] is True
        assert data["edition_reason"] == ""
        assert data["credentials_satisfied"] is True
        assert data["available"] is True

    def test_admin_sources_config_marks_edition_unavailable(self, authed_client, monkeypatch):
        """管理端返回全部源配置，但标注当前 edition 是否允许调度。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        single = authed_client.get(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert single.status_code == 200, single.text
        data = single.json()
        assert data["min_edition"] == "pro"
        assert data["edition_available"] is False
        assert "source 'openalex' requires edition=pro" in data["edition_reason"]
        assert data["credentials_satisfied"] is True
        assert data["available"] is False

        listing = authed_client.get(
            "/api/v1/admin/sources/config",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert listing.status_code == 200, listing.text
        assert listing.json()["openalex"]["edition_available"] is False

    def test_admin_sources_config_marks_no_auth_credentials_satisfied(self, authed_client):
        """免配置源不应显示有 API Key，但应明确标记凭据要求已满足。"""
        resp = authed_client.get(
            "/api/v1/admin/sources/config/arxiv",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["auth_requirement"] == "none"
        assert data["has_api_key"] is False
        assert data["credentials_satisfied"] is True

    def test_admin_sources_config_redacts_secret_channel_overrides(
        self,
        authed_client,
        monkeypatch,
    ):
        """频道级 headers/params 中的敏感字段不应从 admin 配置响应泄漏。"""
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            (
                '{"openalex": {'
                '"headers": {'
                '"Authorization": "Bearer source-secret", '
                '"Cookie": "sid=source-secret", '
                '"X-Trace-Id": "trace-1"'
                "}, "
                '"params": {'
                '"api_key": "param-secret", '
                '"page": 1, '
                '"safe": true'
                "}"
                "}}"
            ),
        )
        from souwen.config import get_config

        get_config.cache_clear()
        resp = authed_client.get(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["headers"] == {
            "Authorization": "***",
            "Cookie": "***",
            "X-Trace-Id": "trace-1",
        }
        assert data["params"] == {"api_key": "***", "page": 1, "safe": True}

        list_resp = authed_client.get(
            "/api/v1/admin/sources/config",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert list_resp.status_code == 200, list_resp.text
        list_data = list_resp.json()["openalex"]
        assert list_data["headers"]["Authorization"] == "***"
        assert list_data["headers"]["Cookie"] == "***"
        assert list_data["headers"]["X-Trace-Id"] == "trace-1"
        assert list_data["params"]["api_key"] == "***"
        assert list_data["params"]["page"] == 1

    def test_admin_source_config_path_strips_source_name(self, authed_client):
        """单源配置 path 参数应先 trim，避免编码空白导致误判未知源。"""
        resp = authed_client.get(
            "/api/v1/admin/sources/config/%20openalex%20",
            headers={"Authorization": "Bearer test-secret-123"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "openalex"

    def test_admin_source_config_update_path_strips_source_name(self, authed_client):
        """单源配置更新 path 参数应先 trim，并写入规范 source 名。"""
        resp = authed_client.put(
            "/api/v1/admin/sources/config/%20openalex%20",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"enabled": False},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["source"] == "openalex"
        readback = authed_client.get(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert readback.status_code == 200, readback.text
        assert readback.json()["enabled"] is False

    @pytest.mark.parametrize("method", ["get", "put"])
    def test_admin_source_config_path_rejects_blank_source_name(self, authed_client, method):
        """单源配置 path 参数 strip 后为空应返回 422，而不是 404 或空写入。"""
        request = getattr(authed_client, method)
        kwargs = {"headers": {"Authorization": "Bearer test-secret-123"}}
        if method == "put":
            kwargs["json"] = {"enabled": False}

        resp = request("/api/v1/admin/sources/config/%20%20%20", **kwargs)

        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"] == "source_name 不能是空字符串"

    def test_admin_source_config_update_trims_proxy(self, authed_client):
        """单源 proxy 应保存校验后的规范值，避免把首尾空白写入运行时配置。"""
        resp = authed_client.put(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"proxy": " http://proxy.example:8080 "},
        )

        assert resp.status_code == 200, resp.text
        readback = authed_client.get(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert readback.status_code == 200, readback.text
        assert readback.json()["proxy"] == "http://proxy.example:8080"

    def test_admin_source_config_redacts_proxy_and_base_url_but_keeps_runtime_value(
        self,
        authed_client,
        monkeypatch,
    ):
        """source config 响应不泄漏 URL secret，运行时配置仍保留真实值。"""
        proxy = "http://user:source-pass@proxy.example:8080?token=source-token&safe=1"
        base_url = "https://source.example/search?apiKey=base-key&safe=1"
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            f'{{"openalex":{{"proxy":"{proxy}","base_url":"{base_url}"}}}}',
        )
        from souwen.config import get_config

        get_config.cache_clear()
        single = authed_client.get(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert single.status_code == 200, single.text
        assert "source-pass" not in single.text
        assert "source-token" not in single.text
        assert "base-key" not in single.text
        assert single.json()["proxy"] == "http://***@proxy.example:8080?token=***&safe=1"
        assert single.json()["base_url"] == "https://source.example/search?apiKey=***&safe=1"

        listing = authed_client.get(
            "/api/v1/admin/sources/config",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert listing.status_code == 200, listing.text
        assert "source-pass" not in listing.text
        assert "base-key" not in listing.text
        assert listing.json()["openalex"]["proxy"] == (
            "http://***@proxy.example:8080?token=***&safe=1"
        )
        assert (
            listing.json()["openalex"]["base_url"]
            == "https://source.example/search?apiKey=***&safe=1"
        )
        assert get_config().sources["openalex"].proxy == proxy
        assert get_config().sources["openalex"].base_url == base_url

    def test_admin_source_config_rejects_redacted_placeholders(self, authed_client):
        """source proxy/base_url 的脱敏占位符不能被提交保存。"""
        proxy_resp = authed_client.put(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"proxy": "http://***@proxy.example:8080?token=***"},
        )
        assert proxy_resp.status_code == 422
        assert "脱敏显示值" in proxy_resp.json()["detail"]

        base_resp = authed_client.put(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"base_url": "https://source.example/search?apiKey=***"},
        )
        assert base_resp.status_code == 422
        assert "脱敏显示值" in base_resp.json()["detail"]

    def test_admin_source_config_update_trims_http_backend(self, authed_client):
        """单源 http_backend 应先 trim，再做允许值校验和保存。"""
        resp = authed_client.put(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"http_backend": " httpx "},
        )

        assert resp.status_code == 200, resp.text
        readback = authed_client.get(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert readback.status_code == 200, readback.text
        assert readback.json()["http_backend"] == "httpx"

    def test_admin_source_config_update_trims_base_url(self, authed_client):
        """单源 base_url 应先 trim，再做 http/https URL 校验和保存。"""
        resp = authed_client.put(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"base_url": " https://api.example.com/v1 "},
        )

        assert resp.status_code == 200, resp.text
        readback = authed_client.get(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert readback.status_code == 200, readback.text
        assert readback.json()["base_url"] == "https://api.example.com/v1"

    def test_admin_source_config_proxy_error_redacts_url_secrets(self, authed_client):
        """单源 proxy 校验错误不应回显 URL userinfo 或敏感 query。"""
        resp = authed_client.put(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
            json={
                "proxy": "ftp://user:pass@proxy.example:21?token=source-proxy-secret&safe=1",
            },
        )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "user:pass" not in detail
        assert "source-proxy-secret" not in detail
        assert "ftp://***@proxy.example:21?token=***&safe=1" in detail

    def test_admin_source_config_base_url_error_redacts_url_secrets(self, authed_client):
        """单源 base_url 校验错误不应回显 URL userinfo 或敏感 query。"""
        resp = authed_client.put(
            "/api/v1/admin/sources/config/openalex",
            headers={"Authorization": "Bearer test-secret-123"},
            json={
                "base_url": "ftp://user:pass@source.example/path?token=base-secret&safe=1",
            },
        )

        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "user:pass" not in detail
        assert "base-secret" not in detail
        assert "ftp://***@source.example/path?token=***&safe=1" in detail

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

    def test_dual_key_user_password_rejected_for_admin(self, dual_key_client):
        """user_password 有效但权限不足，访问管理端点返回 403。"""
        resp = dual_key_client.get(
            "/api/v1/admin/config",
            headers={"Authorization": "Bearer user-pw"},
        )
        assert resp.status_code == 403

    def test_dual_key_no_token_rejected(self, dual_key_client):
        """admin_password 已设时，无 Token 必须 401。"""
        resp = dual_key_client.get("/api/v1/admin/config")
        assert resp.status_code == 401

    # --- admin_password 显式空字符串 → 无管理密码，仍需显式开放 ---
    def test_admin_explicit_empty_stays_locked(self, client, monkeypatch):
        """admin_password="" 时无管理密码，未设 SOUWEN_ADMIN_OPEN 仍锁定。"""
        monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 401

    def test_admin_explicit_empty_can_open_with_admin_open(self, client, monkeypatch):
        """admin_password="" 且 SOUWEN_ADMIN_OPEN=1 时才开放管理端点。"""
        monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "")
        monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 200

    # --- 仅 admin_password 时 user 端开放 ---
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

    def test_sources_guest_only_without_passwords_passthrough(self, client, monkeypatch):
        """guest-only/open-search 部署下，面板登录探针使用的 ``/sources`` 必须可达。"""
        monkeypatch.setenv("SOUWEN_GUEST_ENABLED", "true")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200
        assert set(resp.json()) == {"sources", "categories", "defaults"}

    def test_sources_with_password_requires_token(self, authed_client):
        """设了 user_password 后，``/sources`` 无 Token 直接访问必须 401。"""
        resp = authed_client.get("/api/v1/sources")
        assert resp.status_code == 401

    def test_sources_with_valid_token(self, authed_client):
        """带正确 Token 访问 ``/sources`` 应返回正式 Source Catalog payload。"""
        from souwen.server.schemas import SOURCE_CATEGORY_ORDER

        resp = authed_client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data) == {"sources", "categories", "defaults"}
        assert [item["key"] for item in data["categories"]] == list(SOURCE_CATEGORY_ORDER)
        assert {"arxiv", "crossref", "openalex"} <= set(data["defaults"]["paper:search"])
        openalex = _sources_by_name(data)["openalex"]
        assert openalex["domain"] == "paper"
        assert openalex["category"] == "paper"
        assert openalex["capabilities"] == ["search"]
        assert openalex["auth_requirement"] == "optional"
        assert openalex["credential_fields"] == ["openalex_email"]
        assert openalex["credentials_satisfied"] is True
        assert openalex["configured_credentials"] is False
        assert openalex["risk_level"] == "low"
        assert openalex["stability"] == "stable"
        assert openalex["distribution"] == "core"
        assert openalex["default_for"] == ["paper:search"]
        assert openalex["min_edition"] == "pro"
        assert openalex["edition_available"] is True
        assert openalex["edition_reason"] == ""
        assert openalex["available"] is True

    def test_sources_marks_edition_unavailable_without_hiding_source(self, client, monkeypatch):
        """/sources 保留当前 edition 不可用的源，但标注版本原因且不可调度。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200
        sources = _sources_by_name(resp.json())

        openalex = sources["openalex"]
        assert openalex["min_edition"] == "pro"
        assert openalex["edition_available"] is False
        assert "source 'openalex' requires edition=pro" in openalex["edition_reason"]
        assert openalex["available"] is False

        arxiv = sources["arxiv"]
        assert arxiv["min_edition"] == "basic"
        assert arxiv["edition_available"] is True
        assert arxiv["edition_reason"] == ""
        assert arxiv["available"] is True

    def test_sources_omits_disabled_entries(self, client, monkeypatch):
        """sources.<name>.enabled=false 后，/sources 保留 catalog 条目但标为不可用。"""
        monkeypatch.setenv("SOUWEN_SOURCES", '{"duckduckgo": {"enabled": false}}')
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200
        data = resp.json()
        duckduckgo = _sources_by_name(data)["duckduckgo"]
        assert duckduckgo["available"] is False
        assert duckduckgo["credentials_satisfied"] is True

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
        epo_ops = _sources_by_name(sources_resp.json())["epo_ops"]
        assert epo_ops["category"] == "patent"
        assert epo_ops["configured_credentials"] is False
        assert epo_ops["credentials_satisfied"] is False
        assert epo_ops["available"] is False

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
        source = _sources_by_name(data)[source_name]
        assert source["category"] == "web_general"
        assert source["available"] is True

        module_name, class_name = client_path.split(":")
        client_cls = getattr(importlib.import_module(module_name), class_name)
        instance = client_cls()
        assert instance.instance_url == f"https://{source_name}.example"

    @pytest.mark.parametrize(
        ("source_name", "legacy_field", "client_path"),
        [
            ("searxng", "searxng_url", "souwen.web.searxng:SearXNGClient"),
            ("whoogle", "whoogle_url", "souwen.web.whoogle:WhoogleClient"),
            ("websurfx", "websurfx_url", "souwen.web.websurfx:WebsurfxClient"),
        ],
    )
    def test_sources_self_hosted_legacy_channel_api_key_still_works(
        self,
        client,
        monkeypatch,
        source_name,
        legacy_field,
        client_path,
    ):
        """旧版 sources.<name>.api_key 自建实例 URL 仍应被 catalog 与客户端接受。"""
        import importlib

        monkeypatch.setenv(f"SOUWEN_{legacy_field.upper()}", "")
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            f'{{"{source_name}":{{"api_key":"https://legacy-{source_name}.example"}}}}',
        )
        from souwen.config import get_config

        get_config.cache_clear()
        data = client.get("/api/v1/sources").json()
        source = _sources_by_name(data)[source_name]
        assert source["category"] == "web_general"
        assert source["available"] is True

        module_name, class_name = client_path.split(":")
        client_cls = getattr(importlib.import_module(module_name), class_name)
        assert client_cls().instance_url == f"https://legacy-{source_name}.example"

    @pytest.mark.parametrize(
        ("source_name", "legacy_field"),
        [
            ("searxng", "searxng_url"),
            ("whoogle", "whoogle_url"),
            ("websurfx", "websurfx_url"),
        ],
    )
    def test_admin_source_config_self_hosted_legacy_channel_api_key(
        self,
        client,
        monkeypatch,
        source_name,
        legacy_field,
    ):
        """CLI/admin 共用的凭据 helper 应识别旧版 self-hosted URL 通道。"""
        monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
        monkeypatch.setenv(f"SOUWEN_{legacy_field.upper()}", "")
        monkeypatch.setenv(
            "SOUWEN_SOURCES",
            f'{{"{source_name}":{{"api_key":"https://legacy-{source_name}.example"}}}}',
        )
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get(f"/api/v1/admin/sources/config/{source_name}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_api_key"] is True
        assert data["credentials_satisfied"] is True

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
        source = _sources_by_name(data)["runtime_sources_probe"]
        assert source["category"] == "fetch"
        assert source["distribution"] == "plugin"

        assert _unreg_external("runtime_sources_probe") is True
        data = client.get("/api/v1/sources").json()
        assert "runtime_sources_probe" not in _sources_by_name(data)

    def test_sources_keeps_runtime_web_plugin_without_explicit_category(
        self, client, clean_registry
    ):
        """外部 web 插件不应因缺少 category 声明从 /sources 消失。"""
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
        source = _sources_by_name(data)["runtime_web_sources_probe"]
        assert source["domain"] == "web"
        assert source["category"] == "web_general"

    # --- 双密钥：user 和 admin 密码均可访问搜索端点 ---
    def test_dual_key_user_password_accepted(self, dual_key_client):
        """user_password 可以访问搜索端点。"""
        resp = dual_key_client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer user-pw"},
        )
        assert resp.status_code == 200

    def test_dual_key_admin_password_accepted_on_search(self, dual_key_client):
        """admin_password 也可以访问搜索端点（admin 是 user 超集）。"""
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
        """user_password 已设时，无 Token 必须 401。"""
        resp = dual_key_client.get("/api/v1/sources")
        assert resp.status_code == 401

    def test_guest_enabled_allows_search_without_token(self, client, monkeypatch):
        """guest_enabled=True 时，无 Token 可以访问搜索端点。"""
        monkeypatch.setenv("SOUWEN_USER_PASSWORD", "user-pw")
        monkeypatch.setenv("SOUWEN_GUEST_ENABLED", "true")
        from souwen.config import get_config
        from souwen.web import search as web_search_mod

        async def fake_web_search(q, engines=None, max_results_per_engine=10, **kw):
            return web_search_mod.WebSearchResponse(query=q, source="duckduckgo", results=[])

        get_config.cache_clear()
        monkeypatch.setattr(web_search_mod, "web_search", fake_web_search)
        resp = client.get("/api/v1/search/web?q=foo")
        assert resp.status_code == 200

    def test_guest_enabled_keeps_sources_user_only(self, client, monkeypatch):
        """guest_enabled=True 时，/sources 仍需要 user 或 admin Token。"""
        monkeypatch.setenv("SOUWEN_USER_PASSWORD", "user-pw")
        monkeypatch.setenv("SOUWEN_GUEST_ENABLED", "true")
        from souwen.config import get_config

        get_config.cache_clear()
        no_token = client.get("/api/v1/sources")
        assert no_token.status_code == 401
        user_token = client.get(
            "/api/v1/sources",
            headers={"Authorization": "Bearer user-pw"},
        )
        assert user_token.status_code == 200

    # --- user_password 显式空字符串 → 开放搜索 ---
    def test_user_explicit_empty_opens_search(self, client, monkeypatch):
        """user_password="" 时开放搜索端点。"""
        monkeypatch.setenv("SOUWEN_USER_PASSWORD", "")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/sources")
        assert resp.status_code == 200

    # --- 仅 user_password 时 admin 端仍锁定 ---
    def test_only_user_password_leaves_admin_locked(self, client, monkeypatch):
        """仅设 user_password，管理端点仍需 admin 密码或 SOUWEN_ADMIN_OPEN。"""
        monkeypatch.setenv("SOUWEN_USER_PASSWORD", "user-pw")
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
        assert data["features"]["doctor"] is True
        assert data["features"]["doctor_full"] is False
        assert data["features"]["sources_config_read"] is True
        assert data["features"]["sources_config_write"] is False
        assert data["features"]["config_write"] is False
        assert data["edition"] == "pro"
        assert data["edition_capabilities"]["llm"] is True
        assert "kernel" in data["edition_capabilities"]["warp_modes"]
        assert "firecrawl" in data["edition_capabilities"]["fetch_providers"]
        assert "crawl4ai" not in data["edition_capabilities"]["fetch_providers"]
        assert data["edition_capabilities"]["plugin_preinstalled"] is False
        assert data["admin_password_set"] is False
        assert data["user_password_set"] is False
        assert data["admin_open"] is False

    def test_whoami_basic_edition_capabilities(self, client, monkeypatch):
        """whoami 应单独暴露 edition 能力，不改变角色权限字段语义。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/whoami")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["features"]["search"] is True
        assert data["features"]["fetch"] is False
        assert data["edition"] == "basic"
        assert data["edition_capabilities"] == {
            "llm": False,
            "warp_modes": ["auto", "wireproxy", "external"],
            "fetch_providers": ["builtin", "mcp", "site_crawler"],
            "plugin_preinstalled": False,
        }

    def test_whoami_full_reports_detected_preinstalled_plugins(self, client, monkeypatch):
        """full 版只在当前环境检测到候选插件包时报告预装插件能力。"""
        monkeypatch.setenv("SOUWEN_EDITION", "full")
        monkeypatch.setattr("souwen.editions._plugin_package_importable", lambda name: True)
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/whoami")
        assert resp.status_code == 200
        data = resp.json()
        assert data["edition"] == "full"
        assert data["edition_capabilities"]["plugin_preinstalled"] is True

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
        assert data["admin_password_set"] is False
        assert data["admin_open"] is True

    def test_whoami_admin_open_env_does_not_override_admin_password(self, client, monkeypatch):
        """配置 admin_password 后，即便 SOUWEN_ADMIN_OPEN=1，也不报告无密码 admin-open。"""
        monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "admin-pw")
        monkeypatch.setenv("SOUWEN_ADMIN_OPEN", "1")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/whoami")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["admin_password_set"] is True
        assert data["admin_open"] is False

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
        assert data["admin_password_set"] is True
        assert data["user_password_set"] is True
        assert data["admin_open"] is False

    def test_whoami_user_token(self, dual_key_client):
        """user token 返回 user 角色。"""
        resp = dual_key_client.get(
            "/api/v1/whoami",
            headers={"Authorization": "Bearer user-pw"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["features"]["search"] is True
        assert data["features"]["fetch"] is False
        assert data["features"]["doctor"] is True
        assert data["features"]["doctor_full"] is False
        assert data["features"]["sources_config_read"] is True
        assert data["features"]["sources_config_write"] is False
        assert data["features"]["config_write"] is False
        assert data["admin_password_set"] is True
        assert data["admin_open"] is False

    def test_whoami_rejects_invalid_bearer_in_open_user_mode(self, client):
        """开放用户端点不应把错误 Bearer token 降级成 user。"""
        resp = client.get("/api/v1/whoami", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_whoami_admin_only_invalid_token_rejected(self, client, monkeypatch):
        """仅配置 admin_password 时，错误 token 不能被当作开放 user 登录。"""
        monkeypatch.setenv("SOUWEN_ADMIN_PASSWORD", "admin-pw")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/whoami", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

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
        assert data["admin_password_set"] is True
        assert data["admin_open"] is False

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
# WARP admin route redaction
# ---------------------------------------------------------------------------


class TestWarpAdminRedaction:
    @pytest.mark.parametrize("endpoint", ["/api/v1/admin/warp/config", "/api/v1/admin/warp/modes"])
    def test_warp_external_proxy_redacts_url_secrets(self, authed_client, monkeypatch, endpoint):
        """WARP 外部代理展示值不应泄漏 URL userinfo、query 或 fragment 凭据。"""

        class FakeWarpManager:
            def _has_wireproxy(self):
                return False

            def _has_kernel_wg(self):
                return False

            def _has_usque(self):
                return False

            def _has_warp_cli(self):
                return False

        monkeypatch.setenv(
            "SOUWEN_WARP_EXTERNAL_PROXY",
            (
                "socks5://user:pass@proxy.example:1080"
                "?token=token-secret&region=hk&password=password-secret"
                "&apiKey=camel-api-key-secret&accessToken=camel-access-value"
                "&clientSecret=camel-client-secret&apikey=compact-api-key-secret"
                "&mode=diag;apiKey=semicolon-query-secret"
                "#accessToken=fragment-access-value&tab=status&token=fragment-token"
                ";clientSecret=semicolon-fragment-secret"
            ),
        )
        from souwen.config import get_config
        from souwen.server import warp as warp_mod

        get_config.cache_clear()
        monkeypatch.setattr(
            warp_mod.WarpManager,
            "get_instance",
            classmethod(lambda cls: FakeWarpManager()),
        )

        resp = authed_client.get(
            endpoint,
            headers={"Authorization": "Bearer test-secret-123"},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        if endpoint.endswith("/config"):
            proxy = data["warp_external_proxy"]
        else:
            proxy = next(mode for mode in data["modes"] if mode["id"] == "external")[
                "external_proxy"
            ]
        assert "user:pass" not in proxy
        assert "token-secret" not in proxy
        assert "password-secret" not in proxy
        assert "camel-api-key-secret" not in proxy
        assert "camel-access-value" not in proxy
        assert "camel-client-secret" not in proxy
        assert "compact-api-key-secret" not in proxy
        assert "semicolon-query-secret" not in proxy
        assert "fragment-access-value" not in proxy
        assert "fragment-token" not in proxy
        assert "semicolon-fragment-secret" not in proxy
        assert "socks5://***@proxy.example:1080" in proxy
        assert "token=***" in proxy
        assert "password=***" in proxy
        assert "apiKey=***" in proxy
        assert "accessToken=***" in proxy
        assert "clientSecret=***" in proxy
        assert "apikey=***" in proxy
        assert "region=hk" in proxy
        assert "mode=diag" in proxy
        assert ";apiKey=***" in proxy
        assert "tab=status" in proxy
        assert ";clientSecret=***" in proxy

    def test_warp_status_redacts_secret_last_error(self, authed_client, monkeypatch):
        """WARP 状态中的 last_error 不应泄漏代理凭据或 Bearer token。"""

        class FakeWarpManager:
            def get_status(self):
                return {
                    "status": "error",
                    "mode": "external",
                    "owner": "python",
                    "socks_port": 1080,
                    "http_port": 0,
                    "ip": "",
                    "pid": 0,
                    "interface": None,
                    "last_error": (
                        "proxy socks5://user:pass@proxy.example:1080 failed "
                        "Authorization: Bearer warpsecret123 token=teamsecret "
                        "Cookie: SESSDATA=sess-secret; sid=session-secret "
                        "jwt=jwt-secret session_id=session-id-secret "
                        "callback (https://auth.example/cb?apiKey=url-api-key-secret"
                        "&region=hk#accessToken=url-fragment-access&tab=status). "
                        "retry https://auth.example/retry?token=url-retry-token"
                        "&mode=diag;apiKey=semicolon-text-secret, soon"
                    ),
                    "protocol": "wireguard",
                    "proxy_type": "socks5",
                    "available_modes": {},
                }

        fake = FakeWarpManager()
        from souwen.server import warp as warp_mod

        monkeypatch.setattr(warp_mod.WarpManager, "get_instance", classmethod(lambda cls: fake))
        resp = authed_client.get(
            "/api/v1/admin/warp",
            headers={"Authorization": "Bearer test-secret-123"},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "user:pass" not in data["last_error"]
        assert "warpsecret123" not in data["last_error"]
        assert "teamsecret" not in data["last_error"]
        assert "sess-secret" not in data["last_error"]
        assert "session-secret" not in data["last_error"]
        assert "jwt-secret" not in data["last_error"]
        assert "session-id-secret" not in data["last_error"]
        assert "url-api-key-secret" not in data["last_error"]
        assert "url-fragment-access" not in data["last_error"]
        assert "url-retry-token" not in data["last_error"]
        assert "semicolon-text-secret" not in data["last_error"]
        assert "socks5://***@proxy.example:1080" in data["last_error"]
        assert "apiKey=***" in data["last_error"]
        assert "accessToken=***" in data["last_error"]
        assert "token=***" in data["last_error"]
        assert ";apiKey=***" in data["last_error"]
        assert "region=hk#accessToken=***&tab=status)." in data["last_error"]
        assert "mode=diag;apiKey=***, soon" in data["last_error"]
        assert "region=hk%29" not in data["last_error"]
        assert "mode=diag%2C" not in data["last_error"]
        assert "***" in data["last_error"]

    @pytest.mark.parametrize(
        "endpoint", ["/api/v1/admin/warp/enable", "/api/v1/admin/warp/disable"]
    )
    def test_warp_failure_detail_redacts_secret_error(self, authed_client, monkeypatch, endpoint):
        """WARP 启停失败响应不应把底层错误中的 secret 原样返回。"""

        secret_error = (
            "proxy socks5://user:pass@proxy.example:1080 failed "
            "Authorization: Bearer warpsecret123 token=teamsecret "
            "Cookie: SESSDATA=sess-secret; sid=session-secret "
            "jwt=jwt-secret session_id=session-id-secret "
            "callback (https://auth.example/cb?apiKey=url-api-key-secret"
            "&region=hk#accessToken=url-fragment-access&tab=status). "
            "retry https://auth.example/retry?token=url-retry-token"
            "&mode=diag;apiKey=semicolon-text-secret, soon"
        )

        class FakeWarpManager:
            async def enable(self, **kwargs):
                return {"ok": False, "error": secret_error}

            async def disable(self):
                return {"ok": False, "error": secret_error}

        fake = FakeWarpManager()
        from souwen.server import warp as warp_mod

        monkeypatch.setattr(warp_mod.WarpManager, "get_instance", classmethod(lambda cls: fake))
        resp = authed_client.post(
            endpoint,
            headers={"Authorization": "Bearer test-secret-123"},
        )

        assert resp.status_code == 400, resp.text
        detail = resp.json()["detail"]
        assert "user:pass" not in detail
        assert "warpsecret123" not in detail
        assert "teamsecret" not in detail
        assert "sess-secret" not in detail
        assert "session-secret" not in detail
        assert "jwt-secret" not in detail
        assert "session-id-secret" not in detail
        assert "url-api-key-secret" not in detail
        assert "url-fragment-access" not in detail
        assert "url-retry-token" not in detail
        assert "semicolon-text-secret" not in detail
        assert "socks5://***@proxy.example:1080" in detail
        assert "apiKey=***" in detail
        assert "accessToken=***" in detail
        assert "token=***" in detail
        assert ";apiKey=***" in detail
        assert "region=hk#accessToken=***&tab=status)." in detail
        assert "mode=diag;apiKey=***, soon" in detail
        assert "region=hk%29" not in detail
        assert "mode=diag%2C" not in detail
        assert "***" in detail


class TestWarpEditionPolicy:
    def test_warp_modes_include_edition_metadata_for_basic(self, authed_client, monkeypatch):
        """管理端 modes 仍返回全部模式，但标出当前 edition 是否允许。"""

        class FakeWarpManager:
            def _has_wireproxy(self):
                return True

            def _has_kernel_wg(self):
                return True

            def _has_usque(self):
                return True

            def _has_warp_cli(self):
                return True

        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config
        from souwen.server import warp as warp_mod

        get_config.cache_clear()
        monkeypatch.setattr(
            warp_mod.WarpManager,
            "get_instance",
            classmethod(lambda cls: FakeWarpManager()),
        )

        resp = authed_client.get(
            "/api/v1/admin/warp/modes",
            headers={"Authorization": "Bearer test-secret-123"},
        )

        assert resp.status_code == 200, resp.text
        modes = {item["id"]: item for item in resp.json()["modes"]}
        assert modes["wireproxy"]["min_edition"] == "basic"
        assert modes["wireproxy"]["edition_available"] is True
        assert modes["wireproxy"]["edition_reason"] == ""
        assert modes["usque"]["min_edition"] == "pro"
        assert modes["usque"]["edition_available"] is False
        assert modes["usque"]["edition_reason"] == (
            "WARP mode 'usque' requires edition=pro, current edition=basic"
        )
        assert modes["warp-cli"]["edition_available"] is False

    @pytest.mark.parametrize(
        ("endpoint", "mode"),
        [
            ("/api/v1/admin/warp/enable", "usque"),
            ("/api/v1/admin/warp/switch", "kernel"),
        ],
    )
    def test_warp_start_routes_reject_basic_disallowed_modes_before_manager(
        self, authed_client, monkeypatch, endpoint, mode
    ):
        """basic 下显式启动 pro WARP 模式应返回 403，且不触发启停动作。"""

        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config
        from souwen.server import warp as warp_mod

        get_config.cache_clear()
        monkeypatch.setattr(
            warp_mod.WarpManager,
            "get_instance",
            classmethod(lambda cls: pytest.fail("WarpManager should not be called")),
        )

        resp = authed_client.post(
            endpoint,
            params={"mode": mode},
            headers={"Authorization": "Bearer test-secret-123"},
        )

        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == (
            f"WARP mode '{mode}' requires edition=pro, current edition=basic"
        )


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

    def test_admin_wayback_save_blank_url_returns_422(self, authed_client, monkeypatch):
        """空白 URL 应在请求 schema 层拒绝，避免触发外部存档写入。"""
        calls = []

        class FakeWaybackClient:
            async def save_page(self, url, timeout):
                calls.append({"url": url, "timeout": timeout})
                return SimpleNamespace(success=True, snapshot_url=None, timestamp=None, error=None)

        monkeypatch.setattr("souwen.web.wayback.WaybackClient", FakeWaybackClient)
        resp = authed_client.post(
            "/api/v1/admin/wayback/save",
            headers={"Authorization": "Bearer test-secret-123"},
            json={"url": "   ", "timeout": 10},
        )

        assert resp.status_code == 422
        assert calls == []

    def test_admin_wayback_save_url_is_normalized(self, authed_client, monkeypatch):
        """带首尾空格的 URL 应在调用 WaybackClient 前完成 strip。"""
        calls = []

        class FakeWaybackClient:
            async def save_page(self, url, timeout):
                calls.append({"url": url, "timeout": timeout})
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
            json={"url": " https://example.com ", "timeout": 10},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["url"] == "https://example.com"
        assert calls == [{"url": "https://example.com", "timeout": 10.0}]


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
            ConfigReloadResponse,
            DoctorResponse,
            ErrorResponse,
            HealthResponse,
            SearchMeta,
            SearchPaperResponse,
            SearchPatentResponse,
            SourceCatalogResponse,
        )

        h = HealthResponse(status="ok", version="0.1.0")
        assert h.status == "ok"
        # 确保所有模型可实例化
        assert SearchPaperResponse(query="q", sources=[], results=[], total=0)
        assert SearchPatentResponse(query="q", sources=[], results=[], total=0)
        assert ConfigReloadResponse(status="ok", password_set=True)
        assert DoctorResponse(total=0, ok=0, sources=[])
        assert SourceCatalogResponse()
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

    def test_http_exception_detail_redacts_secrets(self, client):
        """全局 HTTPException 出口不应把结构化 detail 中的 secret 原样返回。"""
        from fastapi import HTTPException

        from souwen.server.app import app

        path = "/__test/http-exception-redaction"

        async def boom():
            raise HTTPException(
                status_code=400,
                detail={
                    "token": "route-secret",
                    "message": "upstream failed Cookie: sid=session-secret",
                    "callback": "https://auth.example/cb?apiKey=url-secret&safe=1",
                },
            )

        app.add_api_route(path, boom, methods=["GET"])
        try:
            resp = client.get(path)
        finally:
            app.router.routes = [
                route for route in app.router.routes if getattr(route, "path", None) != path
            ]

        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "route-secret" not in detail
        assert "session-secret" not in detail
        assert "url-secret" not in detail
        assert "'token': '***'" in detail
        assert "Cookie:***" in detail
        assert "apiKey=***" in detail
        assert "safe=1" in detail


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

    def test_whitespace_q_rejected_all_get_search_routes(self, client):
        """所有 GET 搜索端点都必须拒绝 strip 后为空的 ``q``。"""
        for endpoint in (
            "/api/v1/search/paper",
            "/api/v1/search/patent",
            "/api/v1/search/web",
            "/api/v1/search/news",
            "/api/v1/search/images",
            "/api/v1/search/videos",
        ):
            resp = client.get(endpoint, params={"q": "   "})
            assert resp.status_code == 422

    def test_paper_q_is_trimmed_before_search(self, client, monkeypatch):
        """paper 搜索应把首尾空白裁掉后再调用底层搜索。"""
        import importlib

        search_mod = importlib.import_module("souwen.search")
        captured: dict[str, str] = {}

        async def fake_search(q, sources=None, per_page=10, **kw):
            captured["q"] = q
            return []

        monkeypatch.setattr(search_mod, "search_papers", fake_search)
        resp = client.get("/api/v1/search/paper", params={"q": "  graph rag  "})
        assert resp.status_code == 200
        assert captured["q"] == "graph rag"
        assert resp.json()["query"] == "graph rag"

    def test_patent_q_is_trimmed_before_search(self, client, monkeypatch):
        """patent 搜索应把首尾空白裁掉后再调用底层搜索。"""
        import importlib

        search_mod = importlib.import_module("souwen.search")
        captured: dict[str, str] = {}

        async def fake_search(q, sources=None, per_page=10, **kw):
            captured["q"] = q
            return []

        monkeypatch.setattr(search_mod, "search_patents", fake_search)
        resp = client.get("/api/v1/search/patent", params={"q": "  graph rag  "})
        assert resp.status_code == 200
        assert captured["q"] == "graph rag"
        assert resp.json()["query"] == "graph rag"

    def test_web_q_is_trimmed_before_search(self, client, monkeypatch):
        """web 搜索应把首尾空白裁掉后再调用底层搜索。"""
        from souwen.web import search as web_search_mod

        captured: dict[str, str] = {}

        async def fake_search(q, engines=None, max_results_per_engine=10, **kw):
            captured["q"] = q
            return web_search_mod.WebSearchResponse(
                query=f"provider:{q}",
                source="duckduckgo",
                results=[],
            )

        monkeypatch.setattr(web_search_mod, "web_search", fake_search)
        resp = client.get("/api/v1/search/web", params={"q": "  graph rag  "})
        assert resp.status_code == 200
        assert captured["q"] == "graph rag"
        assert resp.json()["query"] == "graph rag"

    def test_images_q_is_trimmed_before_search(self, client, monkeypatch):
        """image 搜索应把首尾空白裁掉后再调用底层搜索。"""
        import importlib

        from souwen.web import ddg_images as ddg_images_mod

        search_mod = importlib.import_module("souwen.search")
        captured: dict[str, object] = {}

        async def fake_search(
            q,
            domain="paper",
            capability="search",
            sources=None,
            limit=10,
            **kw,
        ):
            captured.update(
                q=q,
                domain=domain,
                capability=capability,
                sources=sources,
                limit=limit,
                region=kw.get("region"),
                safesearch=kw.get("safesearch"),
            )
            return [ddg_images_mod.ImageSearchResponse(query=f"provider:{q}", results=[])]

        monkeypatch.setattr(search_mod, "search", fake_search)
        resp = client.get("/api/v1/search/images", params={"q": "  graph rag  "})
        assert resp.status_code == 200
        assert captured["q"] == "graph rag"
        assert captured["domain"] == "web"
        assert captured["capability"] == "search_images"
        assert captured["sources"] is None
        assert captured["limit"] == 20
        assert captured["region"] == "wt-wt"
        assert captured["safesearch"] == "moderate"
        assert resp.json()["query"] == "graph rag"
        assert resp.json()["meta"]["requested"] == ["duckduckgo_images"]

    def test_images_sources_are_passed_to_registry_search(self, client, monkeypatch):
        """image 搜索的 sources 参数应透传给 registry-backed search。"""
        import importlib

        from souwen.web import ddg_images as ddg_images_mod

        search_mod = importlib.import_module("souwen.search")
        captured: dict[str, object] = {}

        async def fake_search(q, domain="paper", capability="search", sources=None, limit=10, **kw):
            captured["sources"] = sources
            return [ddg_images_mod.ImageSearchResponse(query=q, source="custom_images", results=[])]

        monkeypatch.setattr(search_mod, "search", fake_search)
        resp = client.get(
            "/api/v1/search/images",
            params={"q": "graph", "sources": " custom_images "},
        )
        assert resp.status_code == 200
        assert captured["sources"] == ["custom_images"]
        assert resp.json()["meta"] == {
            "requested": ["custom_images"],
            "succeeded": ["custom_images"],
            "failed": [],
        }

    def test_news_q_is_trimmed_before_search(self, client, monkeypatch):
        """news 搜索应把首尾空白裁掉后再调用 registry-backed search。"""
        import importlib

        from souwen.web import ddg_news as ddg_news_mod

        search_mod = importlib.import_module("souwen.search")
        captured: dict[str, object] = {}

        async def fake_search(
            q,
            domain="paper",
            capability="search",
            sources=None,
            limit=10,
            **kw,
        ):
            captured.update(
                q=q,
                domain=domain,
                capability=capability,
                sources=sources,
                limit=limit,
                region=kw.get("region"),
                safesearch=kw.get("safesearch"),
                time_range=kw.get("time_range"),
            )
            return [
                ddg_news_mod.WebSearchResponse(
                    query=f"provider:{q}",
                    source="duckduckgo_news",
                    results=[],
                )
            ]

        monkeypatch.setattr(search_mod, "search", fake_search)
        resp = client.get("/api/v1/search/news", params={"q": "  graph rag  "})
        assert resp.status_code == 200
        assert captured["q"] == "graph rag"
        assert captured["domain"] == "web"
        assert captured["capability"] == "search_news"
        assert captured["sources"] is None
        assert captured["limit"] == 20
        assert captured["region"] == "wt-wt"
        assert captured["safesearch"] == "moderate"
        assert captured["time_range"] is None
        assert resp.json()["query"] == "graph rag"
        assert resp.json()["engines"] == ["duckduckgo_news"]
        assert resp.json()["meta"]["requested"] == ["duckduckgo_news"]

    def test_news_sources_are_passed_to_registry_search(self, client, monkeypatch):
        """news 搜索的 sources 参数应透传给 registry-backed search。"""
        import importlib

        from souwen.web import ddg_news as ddg_news_mod

        search_mod = importlib.import_module("souwen.search")
        captured: dict[str, object] = {}

        async def fake_search(q, domain="paper", capability="search", sources=None, limit=10, **kw):
            captured["sources"] = sources
            captured["time_range"] = kw.get("time_range")
            return [ddg_news_mod.WebSearchResponse(query=q, source="custom_news", results=[])]

        monkeypatch.setattr(search_mod, "search", fake_search)
        resp = client.get(
            "/api/v1/search/news",
            params={"q": "graph", "sources": " custom_news ", "time_range": "d"},
        )
        assert resp.status_code == 200
        assert captured["sources"] == ["custom_news"]
        assert captured["time_range"] == "d"
        assert resp.json()["engines"] == ["custom_news"]
        assert resp.json()["meta"] == {
            "requested": ["custom_news"],
            "succeeded": ["custom_news"],
            "failed": [],
        }

    def test_videos_q_is_trimmed_before_search(self, client, monkeypatch):
        """video 搜索应把首尾空白裁掉后再调用底层搜索。"""
        import importlib

        from souwen.web import ddg_videos as ddg_videos_mod

        search_mod = importlib.import_module("souwen.search")
        captured: dict[str, object] = {}

        async def fake_search(
            q,
            domain="paper",
            capability="search",
            sources=None,
            limit=10,
            **kw,
        ):
            captured.update(
                q=q,
                domain=domain,
                capability=capability,
                sources=sources,
                limit=limit,
                region=kw.get("region"),
                safesearch=kw.get("safesearch"),
            )
            return [ddg_videos_mod.VideoSearchResponse(query=f"provider:{q}", results=[])]

        monkeypatch.setattr(search_mod, "search", fake_search)
        resp = client.get("/api/v1/search/videos", params={"q": "  graph rag  "})
        assert resp.status_code == 200
        assert captured["q"] == "graph rag"
        assert captured["domain"] == "web"
        assert captured["capability"] == "search_videos"
        assert captured["sources"] is None
        assert captured["limit"] == 20
        assert captured["region"] == "wt-wt"
        assert captured["safesearch"] == "moderate"
        assert resp.json()["query"] == "graph rag"
        assert resp.json()["meta"]["requested"] == ["duckduckgo_videos"]

    def test_videos_sources_are_passed_to_registry_search(self, client, monkeypatch):
        """video 搜索的 sources 参数应透传给 registry-backed search。"""
        import importlib

        from souwen.web import ddg_videos as ddg_videos_mod

        search_mod = importlib.import_module("souwen.search")
        captured: dict[str, object] = {}

        async def fake_search(q, domain="paper", capability="search", sources=None, limit=10, **kw):
            captured["sources"] = sources
            return [ddg_videos_mod.VideoSearchResponse(query=q, source="custom_videos", results=[])]

        monkeypatch.setattr(search_mod, "search", fake_search)
        resp = client.get(
            "/api/v1/search/videos",
            params={"q": "graph", "sources": " custom_videos "},
        )
        assert resp.status_code == 200
        assert captured["sources"] == ["custom_videos"]
        assert resp.json()["meta"] == {
            "requested": ["custom_videos"],
            "succeeded": ["custom_videos"],
            "failed": [],
        }

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

    def test_search_paper_explicit_disallowed_source_returns_403(self, client, monkeypatch):
        """显式请求当前 edition 不可用的 paper source 时应返回 403。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/search/paper?q=foo&sources=openalex")

        assert resp.status_code == 403
        assert "source 'openalex' requires edition=pro" in resp.json()["detail"]

    def test_search_web_explicit_disallowed_engine_returns_403(self, client, monkeypatch):
        """显式请求当前 edition 不可用的 web engine 时应返回 403。"""
        monkeypatch.setenv("SOUWEN_EDITION", "basic")
        from souwen.config import get_config

        get_config.cache_clear()
        resp = client.get("/api/v1/search/web?q=foo&engines=tavily")

        assert resp.status_code == 403
        assert "source 'tavily' requires edition=pro" in resp.json()["detail"]

    def test_web_response_has_meta(self, client, monkeypatch):
        """``/search/web`` 响应必须含 ``meta.requested/succeeded/failed``，并反映每个 engine 的真实命中/失败情况。"""
        from souwen.models import WebSearchResult
        from souwen.web import search as web_search_mod

        async def fake_web_search(q, engines=None, max_results_per_engine=10, **kw):
            return web_search_mod.WebSearchResponse(
                query=q,
                source="duckduckgo",
                results=[
                    WebSearchResult(
                        source="duckduckgo",
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


class TestSearchDefaults:
    """API-SEARCH-DEFAULTS: /search/* 默认源与 registry 保持一致"""

    @staticmethod
    def _register_runtime_default_source(name: str, domain: str) -> None:
        from souwen.registry.adapter import MethodSpec, SourceAdapter
        from souwen.registry.loader import lazy
        from souwen.registry.views import _reg_external

        integration = "scraper" if domain == "web" else "open_api"
        loader_path = {
            "paper": "souwen.paper.arxiv:ArxivClient",
            "patent": "souwen.patent.google_patents:GooglePatentsClient",
            "web": "souwen.web.duckduckgo:DuckDuckGoClient",
        }[domain]
        adapter = SourceAdapter(
            name=name,
            domain=domain,
            integration=integration,
            description=f"runtime {domain} default probe",
            config_field=None,
            client_loader=lazy(loader_path),
            methods={"search": MethodSpec("search")},
            needs_config=False,
            default_for=frozenset({f"{domain}:search"}),
        )
        assert _reg_external(adapter) is True

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
        assert data["sources"] == routes_search._default_paper_sources()
        assert data["meta"]["requested"] == routes_search._default_paper_sources()
        assert data["meta"]["failed"] == routes_search._default_paper_sources()

    def test_paper_default_metadata_uses_live_registry(self, client, monkeypatch, clean_registry):
        """运行时插件声明 ``paper:search`` 默认源后，响应 metadata 必须同步包含它。"""
        import importlib

        from souwen.registry import defaults_for

        self._register_runtime_default_source("runtime_paper_default", "paper")
        search_mod = importlib.import_module("souwen.search")
        captured: dict = {}

        async def fake_search(q, sources=None, per_page=10, **kw):
            captured["sources"] = sources
            return []

        monkeypatch.setattr(search_mod, "search_papers", fake_search)
        resp = client.get("/api/v1/search/paper?q=foo")
        assert resp.status_code == 200
        data = resp.json()
        expected = defaults_for("paper", "search")
        assert captured["sources"] is None
        assert "runtime_paper_default" in expected
        assert data["sources"] == expected
        assert data["meta"]["requested"] == expected
        assert data["meta"]["failed"] == expected

    def test_patent_defaults_come_from_registry(self, client, monkeypatch):
        """未传 ``sources`` 时，专利搜索也应透传 ``None`` 让 registry 默认源生效。"""
        import importlib

        from souwen.server.routes import search as routes_search

        search_mod = importlib.import_module("souwen.search")
        captured: dict = {}

        async def fake_search(q, sources=None, per_page=10, **kw):
            captured["sources"] = sources
            return []

        monkeypatch.setattr(search_mod, "search_patents", fake_search)
        resp = client.get("/api/v1/search/patent?q=foo")
        assert resp.status_code == 200
        data = resp.json()
        assert captured["sources"] is None
        assert data["sources"] == routes_search._default_patent_sources()
        assert data["meta"]["requested"] == routes_search._default_patent_sources()
        assert data["meta"]["failed"] == routes_search._default_patent_sources()

    def test_patent_default_metadata_uses_live_registry(self, client, monkeypatch, clean_registry):
        """运行时插件声明 ``patent:search`` 默认源后，响应 metadata 必须同步包含它。"""
        import importlib

        from souwen.registry import defaults_for

        self._register_runtime_default_source("runtime_patent_default", "patent")
        search_mod = importlib.import_module("souwen.search")
        captured: dict = {}

        async def fake_search(q, sources=None, per_page=10, **kw):
            captured["sources"] = sources
            return []

        monkeypatch.setattr(search_mod, "search_patents", fake_search)
        resp = client.get("/api/v1/search/patent?q=foo")
        assert resp.status_code == 200
        data = resp.json()
        expected = defaults_for("patent", "search")
        assert captured["sources"] is None
        assert "runtime_patent_default" in expected
        assert data["sources"] == expected
        assert data["meta"]["requested"] == expected
        assert data["meta"]["failed"] == expected

    def test_web_defaults_come_from_registry(self, client, monkeypatch):
        """未传 ``engines`` 时，web 搜索应透传 ``None`` 让 registry 默认源生效。"""
        from souwen.server.routes import search as routes_search
        from souwen.web import search as web_search_mod

        captured: dict = {}

        async def fake_web_search(q, engines=None, max_results_per_engine=10, **kw):
            captured["engines"] = engines
            return web_search_mod.WebSearchResponse(query=q, source="duckduckgo", results=[])

        monkeypatch.setattr(web_search_mod, "web_search", fake_web_search)
        resp = client.get("/api/v1/search/web?q=foo")
        assert resp.status_code == 200
        data = resp.json()
        assert captured["engines"] is None
        assert data["engines"] == routes_search._default_web_engines()
        assert data["meta"]["requested"] == routes_search._default_web_engines()
        assert data["meta"]["failed"] == routes_search._default_web_engines()

    def test_web_default_metadata_uses_live_registry(self, client, monkeypatch, clean_registry):
        """运行时插件声明 ``web:search`` 默认源后，响应 metadata 必须同步包含它。"""
        from souwen.registry import defaults_for
        from souwen.web import search as web_search_mod

        self._register_runtime_default_source("runtime_web_default", "web")
        captured: dict = {}

        async def fake_web_search(q, engines=None, max_results_per_engine=10, **kw):
            captured["engines"] = engines
            return web_search_mod.WebSearchResponse(query=q, source="duckduckgo", results=[])

        monkeypatch.setattr(web_search_mod, "web_search", fake_web_search)
        resp = client.get("/api/v1/search/web?q=foo")
        assert resp.status_code == 200
        data = resp.json()
        expected = defaults_for("web", "search")
        assert captured["engines"] is None
        assert "runtime_web_default" in expected
        assert data["engines"] == expected
        assert data["meta"]["requested"] == expected
        assert data["meta"]["failed"] == expected


class TestPerPageAlias:
    """API-PAGE-NAME: /search/web 支持 per_page + max_results"""

    def _patch(self, monkeypatch):
        captured: dict = {}
        from souwen.web import search as web_search_mod

        async def fake_web_search(q, engines=None, max_results_per_engine=10, **kw):
            captured["max"] = max_results_per_engine
            return web_search_mod.WebSearchResponse(query=q, source="duckduckgo", results=[])

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
        assert "source_sha" in data

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
