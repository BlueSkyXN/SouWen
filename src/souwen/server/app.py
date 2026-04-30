"""SouWen FastAPI 应用入口

文件用途：
    FastAPI 应用主文件，负责应用初始化、中间件堆栈配置、异常处理和路由挂载。

主要类/函数：
    lifespan() -> AsyncContextManager
        - 功能：FastAPI 应用生命周期管理（启动/关闭 hooks）
        - 职责：初始化日志、加载配置、协调 WARP 代理、关闭资源
        - 关键逻辑：检测 WARP 状态、管理 session_cache 连接生命周期

    _status_to_code(status_code: int) -> str
        - 功能：HTTP 状态码转机器可读错误码映射
        - 输入：HTTP 状态码（如 404、500）
        - 输出：错误码字符串（如 "not_found"、"internal_error"）

    _get_panel_payload() -> tuple[str, str] | None
        - 功能：读取管理面板 HTML 并计算 ETag（内存缓存）
        - 输入：无
        - 输出：(html_content, etag_value) 或 None
        - 关键优化：ETag 用于浏览器缓存控制，减少冗余传输

    _panel_response(request: Request) -> Response
        - 功能：生成管理面板 HTTP 响应，支持 ETag 和 Cache-Control
        - 输入：FastAPI Request 对象
        - 输出：HTML 响应或 304 Not Modified

    health() -> HealthResponse
        - 功能：健康检查端点 /health，用于探针确认服务存活
        - 返回：{"status": "ok", "version": "..."}

    readiness() -> ReadinessResponse
        - 功能：K8s readiness 探针端点 /readiness，检查本地依赖可用性
        - 不做网络调用，避免探针超时
        - 返回：{"ready": bool, "version": str, "error": str|null}

    panel(request: Request) -> HTMLResponse
        - 功能：获取管理面板（同 /，支持 ETag 缓存）

    root(request: Request) -> HTMLResponse
        - 功能：根路径重定向到管理面板

异常处理器：
    - http_exception_handler：处理 HTTP 异常（4xx/5xx）
    - validation_exception_handler：处理请求验证错误（422）
    - unhandled_exception_handler：捕获未处理异常

中间件堆栈（执行顺序：外层先处理请求，内层先处理响应）：
    1. GZipMiddleware - 响应 GZIP 压缩
    2. CORSMiddleware - CORS（可选，通过配置开启）
    3. RequestIDMiddleware - 请求 ID 和访问日志

模块依赖：
    - fastapi：FastAPI 框架
    - souwen.config：配置管理
    - souwen.server.middleware：请求 ID 和日志中间件
    - souwen.server.routes：API 路由
    - souwen.session_cache：会话缓存
    - souwen.logging_config：日志配置
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from souwen import __version__
from souwen.config import ensure_config_file, get_config
from souwen.logging_config import setup_logging
from souwen.server.auth import is_admin_open_enabled
from souwen.server.middleware import RequestIDMiddleware, get_request_id
from souwen.server.routes import router, admin_router
from souwen.server.schemas import ErrorResponse, HealthResponse, ReadinessResponse

logger = logging.getLogger("souwen.server")

# Panel HTML lookup: installed package → source tree → env override
_PANEL_HTML = Path(__file__).parent / "panel.html"
if not _PANEL_HTML.is_file():
    # Docker: panel.html may be COPY'd to source tree after pip install
    _src_fallback = Path("/app/src/souwen/server/panel.html")
    if _src_fallback.is_file():
        _PANEL_HTML = _src_fallback
_panel_env = os.environ.get("SOUWEN_PANEL_HTML")
if _panel_env:
    _PANEL_HTML = Path(_panel_env)
_panel_cache: str | None = None
_panel_etag: str | None = None
_panel_cache_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 应用生命周期管理（启动和关闭 hooks）

    启动阶段：
        1. 初始化日志系统
        2. 加载配置文件（存在时）
        3. 打印应用版本和密码保护状态
        4. 检测并协调 WARP 代理状态
        5. 记录 WARP 所有者身份（shell/python/none）

    关闭阶段：
        1. 关闭 session_cache 的数据库连接
        2. 记录关闭日志，不干预外部 WARP 进程
    """
    setup_logging()

    path = ensure_config_file()
    if path:
        logger.info("配置文件: %s", path)
    cfg = get_config()
    admin_pw = cfg.effective_admin_password
    user_pw = cfg.effective_user_password
    auth_parts = []
    if admin_pw:
        auth_parts.append("管理员")
    elif is_admin_open_enabled():
        auth_parts.append("管理员(开放)")
    else:
        auth_parts.append("管理员(锁定)")
    if user_pw:
        auth_parts.append("用户")
    if cfg.guest_enabled:
        auth_parts.append("游客(开放)")
    auth_desc = " + ".join(auth_parts)
    logger.info(
        "SouWen %s 启动 | 角色: %s",
        __version__,
        auth_desc,
    )
    if not admin_pw and is_admin_open_enabled():
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

    # MCP Streamable HTTP lifespan（仅在启用时）
    _mcp_http_ctx = None
    if cfg.mcp_http_enabled:
        try:
            from souwen.integrations.mcp.http_server import shttp_lifespan

            _mcp_http_ctx = shttp_lifespan()
            await _mcp_http_ctx.__aenter__()
            logger.info("MCP HTTP 网络端点已启用")
        except ImportError:
            logger.warning("MCP HTTP 已配置启用，但 mcp 依赖未安装，跳过")
            _mcp_http_ctx = None
        except Exception:
            logger.warning("MCP HTTP lifespan 启动失败，跳过", exc_info=True)
            _mcp_http_ctx = None

    yield

    # 关闭 MCP HTTP lifespan
    if _mcp_http_ctx is not None:
        try:
            await _mcp_http_ctx.__aexit__(None, None, None)
        except Exception:
            logger.warning("MCP HTTP lifespan 关闭失败", exc_info=True)

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

# --- MCP 网络端点挂载（可选） ---
_mcp_cfg = get_config()
if _mcp_cfg.mcp_http_enabled:
    try:
        from souwen.integrations.mcp.http_server import create_shttp_app, create_sse_app

        app.mount("/mcp/sse", create_sse_app()) if _mcp_cfg.mcp_http_enable_sse else None
        app.mount("/mcp", create_shttp_app())
        logger.info(
            "MCP 网络端点已挂载: /mcp (SHTTP)%s",
            " + /mcp/sse (SSE)" if _mcp_cfg.mcp_http_enable_sse else "",
        )
    except ImportError:
        logger.warning("MCP HTTP 已配置启用，但 mcp 依赖未安装，跳过挂载")
    except Exception:
        logger.warning("MCP HTTP 子应用创建失败，跳过挂载", exc_info=True)


# --- 全局异常处理器（统一 ErrorResponse 格式）---


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTP 异常处理器 — 将 Starlette HTTPException 转换为统一的 ErrorResponse 格式

    Args:
        request: FastAPI 请求对象
        exc: Starlette HTTPException

    Returns:
        JSONResponse：包含 ErrorResponse 的 JSON 响应，保留原始状态码和响应头
    """
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
    """请求验证错误处理器 — 处理 Pydantic 验证失败（422）

    提取验证错误中的字段和错误消息，格式化为易读的错误描述。

    Args:
        request: FastAPI 请求对象
        exc: RequestValidationError

    Returns:
        JSONResponse：422 响应，包含详细的验证错误信息
    """
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
    """未处理异常捕获器 — 兜底处理任何逃出的异常

    记录完整的异常堆栈和关联的 request_id，返回通用 500 错误响应。

    Args:
        request: FastAPI 请求对象
        exc: 任意异常

    Returns:
        JSONResponse：500 响应，隐藏内部错误细节，仅暴露 request_id 用于日志追踪
    """
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
    """HTTP 状态码转机器可读错误码 — 便于客户端统一处理

    Args:
        status_code: HTTP 状态码（如 404, 500）

    Returns:
        机器可读错误码（如 "not_found", "internal_error"），未知码时返回 "error"
    """
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
    """健康检查端点 /health

    用于容器编排系统（K8s）探针检查服务是否存活。返回当前应用版本。

    Returns:
        HealthResponse: {"status": "ok", "version": "<version>"}
    """
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
    """读取管理面板 HTML 文件并计算 ETag — 支持浏览器缓存

    第一次调用时读取 panel.html、计算 SHA256 ETag、缓存在模块级变量。
    后续调用直接返回缓存，避免重复磁盘 I/O。

    .. note::
        本函数读写模块级 ``_panel_cache`` / ``_panel_etag``，**必须在
        ``_panel_cache_lock`` 持有期间调用**，以避免并发竞态。当前唯一
        调用路径为 ``panel()`` → ``_panel_response()`` → 本函数，锁已
        在 ``panel()`` 中获取。

    Returns:
        tuple[html_content, etag] 或 None（文件不存在时）
    """
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


def _etag_matches(header_value: str, etag: str) -> bool:
    """Check if *etag* matches an ``If-None-Match`` header per RFC 7232.

    Supports the wildcard ``*`` and comma-separated ETag lists.

    判断 ``If-None-Match`` 请求头是否匹配当前 ETag — 用于 304 协商缓存。
    支持通配符 ``*``（匹配任意 ETag）和逗号分隔的 ETag 列表。

    Args:
        header_value: 客户端 ``If-None-Match`` 头原始字符串
        etag: 服务端当前资源的 ETag

    Returns:
        True 表示客户端缓存仍然有效（应返回 304）
    """
    if not header_value:
        return False
    if header_value.strip() == "*":
        return True
    for tag in header_value.split(","):
        if tag.strip() == etag:
            return True
    return False


def _panel_response(request: Request) -> Response:
    """生成管理面板 HTTP 响应，支持 ETag 和 Cache-Control

    检查浏览器的 If-None-Match 头：
    - 若与 ETag 匹配，返回 304 Not Modified
    - 否则返回完整 HTML 和新的 ETag、Cache-Control 头

    Args:
        request: FastAPI Request 对象

    Returns:
        HTMLResponse 或 Response（304 Not Modified）
    """
    payload = _get_panel_payload()
    if payload is None:
        return HTMLResponse("<h1>Panel not found</h1>", status_code=404)
    text, etag = payload
    if _etag_matches(request.headers.get("if-none-match", ""), etag):
        return Response(status_code=304, headers={"ETag": etag})
    return HTMLResponse(
        text,
        headers={"ETag": etag, "Cache-Control": "public, max-age=3600"},
    )


@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def panel(request: Request):
    """管理面板 /panel 端点

    返回管理 Web UI 的 HTML 页面。支持内存缓存和 ETag 条件请求。
    用异步锁保护缓存，避免并发读写问题。

    Args:
        request: FastAPI Request 对象

    Returns:
        HTMLResponse：管理面板 HTML，或 304 Not Modified
    """
    async with _panel_cache_lock:
        return _panel_response(request)


@app.get("/", include_in_schema=False)
async def root():
    """根路径 / 端点 — API 入口

    当 expose_docs 开启时重定向到 Swagger UI (/docs)；
    否则返回 JSON 格式的 API 基本信息。

    Returns:
        RedirectResponse 或 JSONResponse
    """
    if _cfg_at_boot.expose_docs:
        return RedirectResponse(url="/docs", status_code=302)
    return JSONResponse(
        {
            "name": "SouWen API",
            "version": __version__,
            "panel": "/panel",
            "docs": "expose_docs disabled",
        }
    )
