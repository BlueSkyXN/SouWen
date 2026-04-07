"""SouWen FastAPI 应用入口"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from souwen import __version__
from souwen.config import ensure_config_file, get_config
from souwen.server.routes import router, admin_router
from souwen.server.schemas import HealthResponse

logger = logging.getLogger("souwen.server")

_PANEL_HTML = Path(__file__).parent / "panel.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：确保配置文件存在
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
app.include_router(router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1/admin")


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "version": __version__}


@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def panel():
    """管理面板"""
    if _PANEL_HTML.is_file():
        return HTMLResponse(_PANEL_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Panel not found</h1>", status_code=404)
