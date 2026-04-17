"""SouWen FastAPI 应用入口"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from souwen import __version__
from souwen.config import ensure_config_file, get_config
from souwen.logging_config import setup_logging
from souwen.server.middleware import RequestIDMiddleware, get_request_id
from souwen.server.routes import router, admin_router
from souwen.server.schemas import ErrorResponse, HealthResponse, ReadinessResponse

logger = logging.getLogger("souwen.server")

_PANEL_HTML = Path(__file__).parent / "panel.html"
_panel_cache: str | None = None
_panel_etag: str | None = None
_panel_cache_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    path = ensure_config_file()
    if path:
        logger.info("配置文件: %s", path)
    cfg = get_config()
    logger.info(
        "SouWen %s 启动 | 密码保护: %s",
        __version__,
        "已启用" if cfg.api_password else "未启用",
    )
    if (
        not cfg.api_password
        and os.getenv("SOUWEN_ADMIN_OPEN", "").strip().lower() in ("1", "true", "yes", "on")
    ):
        logger.warning(
            "SOUWEN_ADMIN_OPEN=1 已显式解除 Admin API 锁定；"
            "任何能访问 /api/v1/admin/* 的客户端都将获得管理员权限，生产环境禁用。"
        )

    # WARP 状态协调 (检测 shell entrypoint 启动的 WARP 实例)
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

    yield

    # 关闭会话缓存的 aiosqlite 连接
    try:
        from souwen.session_cache import get_session_cache

        await get_session_cache().aclose()
    except Exception:
        logger.warning("关闭 session_cache 失败", exc_info=True)

    # 关停日志：不干预外部 WARP 进程
    try:
        owner = warp_mgr._state.owner if warp_mgr is not None else "unknown"
    except Exception:
        owner = "unknown"
    logger.info("SouWen shutting down; WARP owner=%s (不干预外部进程)", owner)


_cfg_at_boot = get_config()
_fastapi_kwargs: dict = {
    "title": "SouWen API",
    "description": "面向 AI Agent 的学术论文 + 专利 + 网页统一搜索 API",
    "version": __version__,
    "lifespan": lifespan,
}
if not _cfg_at_boot.expose_docs:
    _fastapi_kwargs.update(docs_url=None, redoc_url=None, openapi_url=None)

app = FastAPI(**_fastapi_kwargs)

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

# 3. Request ID + 访问日志（最外层 ASGI 中间件）
app.add_middleware(RequestIDMiddleware)

app.include_router(router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1/admin")


# --- 全局异常处理器（统一 ErrorResponse 格式）---


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=_status_to_code(exc.status_code),
            detail=str(exc.detail),
            request_id=get_request_id(),
        ).model_dump(),
        headers=getattr(exc, "headers", None) or None,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    fields = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", []))
        fields.append(f"{loc}: {err.get('msg', '')}")
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="validation_error",
            detail="; ".join(fields) if fields else str(exc),
            request_id=get_request_id(),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
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
    """HTTP 状态码 → 机器可读错误码"""
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


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "version": __version__}


@app.get("/readiness", response_model=ReadinessResponse)
async def readiness():
    """K8s readiness 探针：仅做本地检查（配置可加载 + 数据源注册表非空）。

    不做任何网络调用，避免探针超时。
    """
    try:
        get_config()
        from souwen.source_registry import get_all_sources

        sources = get_all_sources()
        if not sources:
            return JSONResponse(
                status_code=503,
                content=ReadinessResponse(
                    ready=False,
                    version=__version__,
                    error="source registry is empty",
                ).model_dump(),
            )
        return {"ready": True, "version": __version__, "error": None}
    except Exception as exc:  # pragma: no cover - 防御性
        return JSONResponse(
            status_code=503,
            content=ReadinessResponse(
                ready=False,
                version=__version__,
                error=f"{type(exc).__name__}: {exc}",
            ).model_dump(),
        )


def _get_panel_payload() -> tuple[str, str] | None:
    """读取 panel.html 并计算 ETag（缓存在模块级变量里）。"""
    global _panel_cache, _panel_etag
    if _panel_cache is not None and _panel_etag is not None:
        return _panel_cache, _panel_etag
    if not _PANEL_HTML.is_file():
        return None
    text = _PANEL_HTML.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    _panel_cache = text
    _panel_etag = f'"{digest}"'
    return _panel_cache, _panel_etag


def _panel_response(request: Request) -> Response:
    payload = _get_panel_payload()
    if payload is None:
        return HTMLResponse("<h1>Panel not found</h1>", status_code=404)
    text, etag = payload
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return HTMLResponse(
        text,
        headers={"ETag": etag, "Cache-Control": "public, max-age=3600"},
    )


@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def panel(request: Request):
    """管理面板（内存缓存 + ETag/Cache-Control）"""
    async with _panel_cache_lock:
        return _panel_response(request)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    """根路径返回管理面板（同 /panel，支持 ETag）"""
    async with _panel_cache_lock:
        return _panel_response(request)
