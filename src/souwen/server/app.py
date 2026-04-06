"""SouWen FastAPI 应用入口"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from souwen import __version__
from souwen.config import ensure_config_file, get_config
from souwen.server.routes import router, admin_router

logger = logging.getLogger("souwen.server")


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
    yield


app = FastAPI(
    title="SouWen API",
    description="面向 AI Agent 的学术论文 + 专利 + 网页统一搜索 API",
    version=__version__,
    lifespan=lifespan,
)
app.include_router(router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1/admin")


@app.get("/health")
async def health():
    return {"status": "ok", "version": __version__}
