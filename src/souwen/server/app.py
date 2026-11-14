"""SouWen FastAPI 应用入口"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from souwen import __version__
from souwen.agent import AgentRuntime
from souwen.config import ensure_config_file, get_config
from souwen.common_runtime.observability import get_request_id
from souwen.common_runtime.provider_support.redaction import redact_secret_text, redact_secret_value
from souwen.logging_config import setup_logging
from souwen.server.agent_api import create_agent_api_router
from souwen.server.auth import McpAuthMiddleware, check_target_user_auth
from souwen.server.limiter import rate_limit_target_data
from souwen.server.middleware import RequestIDMiddleware
from souwen.server.mcp_server import build_mcp_server
from souwen.server.schemas import ErrorResponse
from souwen.server.v2_runtime import TargetRuntime, build_target_runtime

logger = logging.getLogger("souwen.server")

_cfg_at_boot = get_config()
_target_runtime: TargetRuntime = build_target_runtime(_cfg_at_boot)
_agent_runtime = AgentRuntime(_target_runtime, _cfg_at_boot)
_mcp_server = build_mcp_server(_agent_runtime)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 应用生命周期管理（启动和关闭 hooks）

    启动阶段：日志 → 配置 → WARP 状态协调 → MCP session manager。
    关闭阶段：target runtime → session cache → 关停日志（不干预外部 WARP 进程）。
    """
    setup_logging()

    path = ensure_config_file()
    if path:
        logger.info("配置文件: %s", path)
    warp_mgr = None
    try:
        from souwen.server.warp import WarpManager

        warp_mgr = WarpManager.get_instance()
        await warp_mgr.reconcile()
        st = warp_mgr._state
        logger.info(
            "WARP state: owner=%s mode=%s status=%s",
            st.owner,
            st.mode,
            st.status,
        )
    except Exception:
        logger.warning("WARP 状态协调失败，跳过", exc_info=True)

    async with _mcp_server.session_manager.run():
        yield

        if _target_runtime is not None:
            try:
                await _target_runtime.close()
            except Exception:
                logger.warning("Target runtime 关闭失败", exc_info=True)

        try:
            from souwen.common_runtime.provider_support.session_cache import get_session_cache

            await get_session_cache().aclose()
        except Exception:
            logger.warning("关闭 session_cache 失败", exc_info=True)

        try:
            from souwen.common_runtime.provider_support.browser_fetch import close_shared_pools

            await close_shared_pools()
        except Exception:
            logger.warning("关闭浏览器池失败", exc_info=True)

        try:
            owner = warp_mgr._state.owner if warp_mgr is not None else "unknown"
        except Exception:
            owner = "unknown"
        logger.info("SouWen shutting down; WARP owner=%s (不干预外部进程)", owner)


_fastapi_kwargs: dict = {
    "title": "SouWen API",
    "description": "给 Agent 用的免费搜索与抓取 API：search 与 fetch 两个动作",
    "version": __version__,
    "lifespan": lifespan,
}
if not _cfg_at_boot.expose_docs:
    _fastapi_kwargs.update(docs_url=None, redoc_url=None, openapi_url=None)

app = FastAPI(**_fastapi_kwargs)
app.state.target_runtime = _target_runtime
app.state.agent_runtime = _agent_runtime

# --- Middleware (执行顺序：外层先处理请求，内层先处理响应) ---
# 1. GZip 压缩（最内层，压缩响应体）
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 2. CORS — 默认关闭，通过配置开启
cfg = get_config()
if cfg.cors_origins:
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# 3. Request ID + 访问日志
app.add_middleware(RequestIDMiddleware)

# 4. /mcp 是原始 ASGI 挂载，FastAPI 依赖保护不到，用同一套 user 凭据校验兜住
app.add_middleware(McpAuthMiddleware)

app.include_router(
    create_agent_api_router(
        _agent_runtime,
        require_user=check_target_user_auth,
        rate_limit=rate_limit_target_data,
    )
)


@app.get("/healthz", operation_id="healthz")
async def healthz():
    """探针端点 — 仅确认进程存活，不做依赖检查"""
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "request_id": get_request_id(),
        }
    )


# --- 全局异常处理器（统一 ErrorResponse 格式）---


def _safe_error_detail(detail: object) -> str:
    """Redact secrets from API-facing error details before serialization."""
    safe_detail = redact_secret_value(detail)
    text = redact_secret_text(str(safe_detail))
    return text or ""


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP 异常处理器 — 将 Starlette HTTPException 转换为统一的 ErrorResponse 格式"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=_status_to_code(exc.status_code),
            detail=_safe_error_detail(exc.detail),
            request_id=get_request_id(),
        ).model_dump(),
        headers=getattr(exc, "headers", None) or None,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求验证错误处理器 — 处理 Pydantic 验证失败（422）"""
    fields = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", []))
        fields.append(f"{loc}: {err.get('msg', '')}")
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="validation_error",
            detail=_safe_error_detail("; ".join(fields) if fields else exc),
            request_id=get_request_id(),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未处理异常捕获器 — 兜底处理任何逃出的异常"""
    rid = get_request_id()
    logger.exception("未处理异常 [%s]", rid)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            detail="服务内部错误，请稍后重试",
            request_id=rid,
        ).model_dump(),
    )


def _status_to_code(status_code: int) -> str:
    """HTTP 状态码转机器可读错误码 — 便于客户端统一处理"""
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        502: "bad_gateway",
        503: "service_unavailable",
        504: "gateway_timeout",
    }.get(status_code, "error")


@app.get("/", include_in_schema=False)
async def root():
    """根路径 / 端点 — API 入口"""
    if _cfg_at_boot.expose_docs:
        return RedirectResponse(url="/docs", status_code=302)
    return JSONResponse(
        {
            "name": "SouWen API",
            "version": __version__,
            "tools": ["search", "fetch"],
            "mcp": "/mcp",
            "docs": "expose_docs disabled",
        }
    )


# MCP streamable HTTP：根挂载，内层 Route 的 /mcp 与其它已注册路由自然组合。
# 必须放在所有 FastAPI 路由之后，避免遮蔽 /search、/fetch、/sources、/healthz。
app.mount("/", _mcp_server.streamable_http_app())
