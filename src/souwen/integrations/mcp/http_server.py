"""SouWen MCP 网络传输层 — Streamable HTTP + SSE

为现有 MCP stdio 服务端新增网络可达能力，支持：
- Streamable HTTP (SHTTP)：挂载于 /mcp，基于 StreamableHTTPSessionManager
- SSE (Server-Sent Events)：挂载于 /mcp/sse，基于 SseServerTransport

关键设计：
    1. 复用 create_server() 作为工具定义与调用内核，无需重复注册工具。
    2. 提供 ASGI middleware 实现 Bearer Token 鉴权，
       复用 souwen.server.auth.resolve_role / Role 逻辑。
    3. 提供可挂载到 FastAPI 的 ASGI app，通过 lifespan 管理 session_manager 生命周期。

生命周期管理：
    session_manager 在每次 lifespan 进入时 *重新创建*，确保 reload / 多次启停
    不会复用已经关闭的 manager 实例。ASGI handler 在 manager 尚未就绪时返回 503。

鉴权规则：
    - Role.USER 及以上可访问（Admin 当然可）
    - Guest 即使开启也不允许访问 MCP 网络端点
    - 若系统处于全开放（无 user/admin 密码）则允许访问
"""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from souwen.config import get_config

logger = logging.getLogger("souwen.mcp.http")

# ---------------------------------------------------------------------------
# ASGI 鉴权中间件 — 不走 FastAPI Depends，在子应用边界拦截
# ---------------------------------------------------------------------------


class MCPAuthMiddleware:
    """Bearer Token ASGI 中间件，复用现有认证逻辑。

    规则：
    - 无 user/admin 密码 → 全开放，允许访问
    - 有密码时，需 Bearer Token 匹配 user 或 admin 密码
    - Guest 角色不允许访问 MCP 网络端点
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cfg = get_config()
        admin_pw = cfg.effective_admin_password or ""
        user_pw = cfg.effective_user_password or ""

        # 全开放模式：无密码配置 → 放行
        if not admin_pw and not user_pw:
            await self.app(scope, receive, send)
            return

        # 提取 Bearer Token
        token = _extract_bearer_token(scope)

        # 恒定时间比较 — 始终执行两次，消除时序旁路
        is_admin = bool(admin_pw) and secrets.compare_digest(token, admin_pw)
        is_user = bool(user_pw) and secrets.compare_digest(token, user_pw)

        if is_admin or is_user:
            await self.app(scope, receive, send)
            return

        # 拒绝：guest 或无效 token
        response = JSONResponse(
            {"error": "unauthorized", "detail": "MCP 网络端点需要有效的 Bearer Token"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)


def _extract_bearer_token(scope: Scope) -> str:
    """从 ASGI scope 的 headers 中提取 Bearer token"""
    for key, value in scope.get("headers", []):
        if key == b"authorization":
            decoded = value.decode("latin-1", errors="replace")
            if decoded.lower().startswith("bearer "):
                return decoded[7:].strip()
            break
    return ""


# ---------------------------------------------------------------------------
# SHTTP 应用工厂
# ---------------------------------------------------------------------------

_session_manager = None  # 模块级引用，每次 lifespan 周期重建


def get_session_manager():
    """返回当前 StreamableHTTPSessionManager 实例（lifespan 启动后可用）"""
    return _session_manager


def _create_session_manager():
    """(重)创建 StreamableHTTPSessionManager，保证每次 lifespan 得到全新实例。"""
    global _session_manager

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    from souwen.integrations.mcp.server import create_server

    cfg = get_config()
    server = create_server()
    _session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=cfg.mcp_http_json_response,
        stateless=cfg.mcp_http_stateless,
    )
    return _session_manager


def create_shttp_app() -> Starlette:
    """创建 Streamable HTTP MCP 子应用

    返回一个可通过 app.mount("/mcp", ...) 挂载的 Starlette ASGI 应用。
    内含 MCPAuthMiddleware 鉴权层。

    注意：session_manager 不在此处创建，而是由 ``shttp_lifespan()`` 在
    FastAPI 启动时创建。若请求到达时 manager 尚未就绪，返回 503。

    Returns:
        Starlette ASGI app
    """

    # 使用低层 ASGI 路由，让 session_manager 直接控制响应
    async def mcp_asgi(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            response = Response("Not Found", status_code=404)
            await response(scope, receive, send)
            return
        mgr = get_session_manager()
        if mgr is None:
            response = JSONResponse(
                {"error": "service_unavailable", "detail": "MCP 尚未就绪"},
                status_code=503,
            )
            await response(scope, receive, send)
            return
        await mgr.handle_request(scope, receive, send)

    shttp_app = Starlette(
        routes=[
            Mount("/", app=mcp_asgi),
        ],
    )
    shttp_app.add_middleware(MCPAuthMiddleware)
    return shttp_app


# ---------------------------------------------------------------------------
# SSE 应用工厂
# ---------------------------------------------------------------------------


def create_sse_app() -> Starlette:
    """创建 SSE MCP 子应用

    按 MCP SDK 示例路由实现：
    - GET /  → SSE 连接（connect_sse）
    - POST /messages → 消息接收（handle_post_message）

    挂载到 /mcp/sse 后，客户端通过 GET /mcp/sse 建立连接，
    POST /mcp/sse/messages 发送消息。

    Returns:
        Starlette ASGI app
    """
    from mcp.server.sse import SseServerTransport

    from souwen.integrations.mcp.server import create_server

    sse_transport = SseServerTransport("/messages")

    async def handle_sse_connection(scope: Scope, receive: Receive, send: Send) -> None:
        """GET / → 建立 SSE 连接并运行 MCP 服务器"""
        server = create_server()
        async with sse_transport.connect_sse(scope, receive, send) as (
            read_stream,
            write_stream,
        ):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    async def handle_sse_post(scope: Scope, receive: Receive, send: Send) -> None:
        """POST /messages → 接收客户端消息"""
        await sse_transport.handle_post_message(scope, receive, send)

    sse_app = Starlette(
        routes=[
            Route("/", endpoint=handle_sse_connection, methods=["GET"]),
            Route("/messages", endpoint=handle_sse_post, methods=["POST"]),
        ],
    )
    sse_app.add_middleware(MCPAuthMiddleware)
    return sse_app


# ---------------------------------------------------------------------------
# lifespan 辅助 — 在 FastAPI 主 lifespan 中调用
# ---------------------------------------------------------------------------


@asynccontextmanager
async def shttp_lifespan():
    """管理 StreamableHTTPSessionManager 生命周期

    每次进入时 **重新创建** manager，确保 uvicorn reload / 多次启停
    不会复用已关闭的旧 manager。退出时将模块级引用置空。
    若 MCP 依赖未安装（ImportError），则为 no-op。
    """
    global _session_manager
    try:
        mgr = _create_session_manager()
    except Exception:
        logger.warning("无法创建 MCP session manager，跳过", exc_info=True)
        yield
        return
    try:
        async with mgr.run():
            logger.info("MCP Streamable HTTP session manager 已启动")
            yield
    finally:
        _session_manager = None
        logger.info("MCP Streamable HTTP session manager 已关闭")
