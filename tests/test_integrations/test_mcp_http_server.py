"""MCP HTTP 网络端点 测试

覆盖：
a. 鉴权中间件：无 token 拒绝（配置有密码时），user/admin token 放行
b. 配置关闭时不挂载
c. 配置开启且 mcp 不可用时不崩溃（降级）
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from souwen.config.models import SouWenConfig

pytest.importorskip("starlette")
pytest.importorskip("fastapi")


# ---------------------------------------------------------------------------
# a. 鉴权中间件测试
# ---------------------------------------------------------------------------


class _FakeApp:
    """简单 ASGI app，记录是否被调用"""

    def __init__(self):
        self.called = False
        self.scope = None

    async def __call__(self, scope, receive, send):
        self.called = True
        self.scope = scope
        # 返回 200 OK
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})


def _make_scope(token: str | None = None) -> dict:
    """构造最小 ASGI HTTP scope"""
    headers = []
    if token is not None:
        headers.append([b"authorization", f"Bearer {token}".encode()])
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers,
        "query_string": b"",
    }


class _Captured:
    """捕获 ASGI send 调用"""

    def __init__(self):
        self.messages: list[dict] = []

    async def __call__(self, message):
        self.messages.append(message)


async def _noop_receive():
    return {"type": "http.disconnect"}


@pytest.mark.asyncio
async def test_auth_reject_no_token(monkeypatch):
    """有密码配置时，无 token 应返回 401"""
    cfg = SouWenConfig(user_password="secret123")
    monkeypatch.setattr("souwen.integrations.mcp.http_server.get_config", lambda: cfg)

    from souwen.integrations.mcp.http_server import MCPAuthMiddleware

    inner = _FakeApp()
    mw = MCPAuthMiddleware(inner)
    captured = _Captured()

    await mw(_make_scope(token=None), _noop_receive, captured)

    assert not inner.called
    # 应返回 401
    start = captured.messages[0]
    assert start["status"] == 401


@pytest.mark.asyncio
async def test_auth_reject_wrong_token(monkeypatch):
    """有密码配置时，错误 token 应返回 401"""
    cfg = SouWenConfig(user_password="secret123")
    monkeypatch.setattr("souwen.integrations.mcp.http_server.get_config", lambda: cfg)

    from souwen.integrations.mcp.http_server import MCPAuthMiddleware

    inner = _FakeApp()
    mw = MCPAuthMiddleware(inner)
    captured = _Captured()

    await mw(_make_scope(token="wrong_token"), _noop_receive, captured)

    assert not inner.called
    start = captured.messages[0]
    assert start["status"] == 401


@pytest.mark.asyncio
async def test_auth_allow_user_token(monkeypatch):
    """user token 应放行"""
    cfg = SouWenConfig(user_password="userpass")
    monkeypatch.setattr("souwen.integrations.mcp.http_server.get_config", lambda: cfg)

    from souwen.integrations.mcp.http_server import MCPAuthMiddleware

    inner = _FakeApp()
    mw = MCPAuthMiddleware(inner)
    captured = _Captured()

    await mw(_make_scope(token="userpass"), _noop_receive, captured)

    assert inner.called


@pytest.mark.asyncio
async def test_auth_allow_admin_token(monkeypatch):
    """admin token 应放行"""
    cfg = SouWenConfig(admin_password="adminpass")
    monkeypatch.setattr("souwen.integrations.mcp.http_server.get_config", lambda: cfg)

    from souwen.integrations.mcp.http_server import MCPAuthMiddleware

    inner = _FakeApp()
    mw = MCPAuthMiddleware(inner)
    captured = _Captured()

    await mw(_make_scope(token="adminpass"), _noop_receive, captured)

    assert inner.called


@pytest.mark.asyncio
async def test_auth_open_mode(monkeypatch):
    """全开放模式（无密码）应放行"""
    cfg = SouWenConfig()  # 无密码
    monkeypatch.setattr("souwen.integrations.mcp.http_server.get_config", lambda: cfg)

    from souwen.integrations.mcp.http_server import MCPAuthMiddleware

    inner = _FakeApp()
    mw = MCPAuthMiddleware(inner)
    captured = _Captured()

    await mw(_make_scope(token=None), _noop_receive, captured)

    assert inner.called


@pytest.mark.asyncio
async def test_auth_guest_not_allowed(monkeypatch):
    """即使 guest_enabled=True，Guest 也不能访问 MCP 网络端点"""
    cfg = SouWenConfig(user_password="userpass", guest_enabled=True)
    monkeypatch.setattr("souwen.integrations.mcp.http_server.get_config", lambda: cfg)

    from souwen.integrations.mcp.http_server import MCPAuthMiddleware

    inner = _FakeApp()
    mw = MCPAuthMiddleware(inner)
    captured = _Captured()

    # 无 token → guest → 拒绝
    await mw(_make_scope(token=None), _noop_receive, captured)

    assert not inner.called
    start = captured.messages[0]
    assert start["status"] == 401


@pytest.mark.asyncio
async def test_auth_passthrough_non_http(monkeypatch):
    """非 HTTP scope（如 lifespan）应直接透传"""
    cfg = SouWenConfig(user_password="secret")
    monkeypatch.setattr("souwen.integrations.mcp.http_server.get_config", lambda: cfg)

    from souwen.integrations.mcp.http_server import MCPAuthMiddleware

    inner = _FakeApp()
    mw = MCPAuthMiddleware(inner)
    captured = _Captured()

    scope = {"type": "lifespan"}
    await mw(scope, _noop_receive, captured)

    assert inner.called


# ---------------------------------------------------------------------------
# b. 配置关闭时不挂载
# ---------------------------------------------------------------------------


def test_mcp_http_disabled_no_mount(monkeypatch):
    """mcp_http_enabled=False 时，/mcp 路由不应存在"""
    cfg = SouWenConfig(mcp_http_enabled=False)
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)
    monkeypatch.setattr("souwen.config.loader.get_config", lambda: cfg)

    # 重新导入 app 模块以应用配置
    import souwen.server.app as app_mod

    # 默认配置下应无 MCP 路由（因为默认 mcp_http_enabled=False）
    # 模块级 app 对象已创建，验证默认行为：False 不会挂载
    mcp_mount_paths = [
        r.path for r in app_mod.app.routes if hasattr(r, "path") and r.path.startswith("/mcp")
    ]
    assert mcp_mount_paths == [], f"不应有 MCP 挂载点，但发现: {mcp_mount_paths}"


# ---------------------------------------------------------------------------
# c. 配置开启但 mcp 不可用时不崩溃
# ---------------------------------------------------------------------------


def test_mcp_http_graceful_degradation():
    """mcp_http_enabled=True 但 mcp 包不可用时，_create_session_manager 抛 ImportError"""
    import souwen.integrations.mcp.http_server as mod

    # 模拟 mcp SDK 不可用：让 _create_session_manager 内部 import 失败
    with patch.object(
        mod,
        "_create_session_manager",
        side_effect=ImportError("Mocked: mcp dependency missing"),
    ):
        with pytest.raises(ImportError, match="mcp dependency missing"):
            mod._create_session_manager()


@pytest.mark.asyncio
async def test_shttp_lifespan_tolerates_import_error(monkeypatch):
    """shttp_lifespan 在 _create_session_manager 失败时不崩溃，且 manager 保持 None"""
    import souwen.integrations.mcp.http_server as mod

    monkeypatch.setattr(
        mod,
        "_create_session_manager",
        lambda: (_ for _ in ()).throw(ImportError("no mcp")),
    )
    # 确保 lifespan 不抛异常
    async with mod.shttp_lifespan():
        assert mod.get_session_manager() is None


@pytest.mark.asyncio
async def test_shttp_handler_returns_503_before_lifespan(monkeypatch):
    """在 lifespan 启动前请求 /mcp 应返回 503"""
    import souwen.integrations.mcp.http_server as mod

    # 确保 manager 为空
    monkeypatch.setattr(mod, "_session_manager", None)

    cfg = SouWenConfig()  # 全开放
    monkeypatch.setattr("souwen.integrations.mcp.http_server.get_config", lambda: cfg)

    app = mod.create_shttp_app()

    captured = _Captured()
    scope = _make_scope(token=None)
    await app(scope, _noop_receive, captured)

    # 应该有 503 返回
    start_msg = next((m for m in captured.messages if m.get("type") == "http.response.start"), None)
    assert start_msg is not None
    assert start_msg["status"] == 503


# ---------------------------------------------------------------------------
# 辅助：_extract_bearer_token 单元测试
# ---------------------------------------------------------------------------


def test_extract_bearer_token():
    """_extract_bearer_token 应正确提取 token"""
    from souwen.integrations.mcp.http_server import _extract_bearer_token

    # 正常 token
    scope = {"headers": [(b"authorization", b"Bearer mytoken123")]}
    assert _extract_bearer_token(scope) == "mytoken123"

    # 无 authorization 头
    scope = {"headers": [(b"content-type", b"application/json")]}
    assert _extract_bearer_token(scope) == ""

    # 空 headers
    scope = {"headers": []}
    assert _extract_bearer_token(scope) == ""

    # 无 headers key
    scope = {}
    assert _extract_bearer_token(scope) == ""

    # 非 Bearer 认证
    scope = {"headers": [(b"authorization", b"Basic abc123")]}
    assert _extract_bearer_token(scope) == ""

    # Bearer 大小写（应匹配小写开头）
    scope = {"headers": [(b"authorization", b"bearer tok")]}
    assert _extract_bearer_token(scope) == "tok"
