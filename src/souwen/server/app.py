"""SouWen FastAPI 应用入口"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from souwen import __version__
from souwen.config import ensure_config_file, get_config
from souwen.logging_config import setup_logging
from souwen.server.middleware import RequestIDMiddleware, get_request_id
from souwen.server.routes import router, admin_router
from souwen.server.schemas import ErrorResponse, HealthResponse

logger = logging.getLogger("souwen.server")

_PANEL_HTML = Path(__file__).parent / "panel.html"
_panel_cache: str | None = None


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

    # WARP 状态协调 (检测 shell entrypoint 启动的 WARP 实例)
    try:
        from souwen.server.warp import WarpManager

        warp_mgr = WarpManager.get_instance()
        await warp_mgr.reconcile()
    except Exception:
        logger.warning("WARP 状态协调失败，跳过", exc_info=True)

    yield


app = FastAPI(
    title="SouWen API",
    description="面向 AI Agent 的学术论文 + 专利 + 网页统一搜索 API",
    version=__version__,
    lifespan=lifespan,
)

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
        502: "upstream_error",
    }.get(status_code, "error")


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "version": __version__}


@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def panel():
    """管理面板（首次访问后缓存在内存中）"""
    global _panel_cache
    if _panel_cache is None:
        if _PANEL_HTML.is_file():
            _panel_cache = _PANEL_HTML.read_text(encoding="utf-8")
        else:
            return HTMLResponse("<h1>Panel not found</h1>", status_code=404)
    return HTMLResponse(_panel_cache)
