"""SouWen API 路由 — 子模块聚合

按职责将原先单文件 ``routes.py`` 拆分为多个子模块：

    search    — /search/*  论文/专利/网页/图片/视频
    fetch     — /fetch、/links、/sitemap
    youtube   — /youtube/*
    wayback   — /wayback/cdx、/wayback/check
    bilibili  — /bilibili/*  （原 ``routes_bilibili.py``）
    sources   — /sources
    admin/    — 管理端（统一 ``require_auth``）

外部继续使用 ``from souwen.server.routes import router, admin_router`` 即可，
两个聚合路由保持原行为：

    router        - 公开路由（含 bilibili），被挂在 /api/v1
    admin_router  - 管理路由，被挂在 /api/v1/admin
"""

from __future__ import annotations

from fastapi import APIRouter

from souwen.server.routes.admin import admin_router
from souwen.server.routes.bilibili import router as bilibili_router
from souwen.server.routes.fetch import router as fetch_router
from souwen.server.routes.search import router as search_router
from souwen.server.routes.sources import router as sources_router
from souwen.server.routes.wayback import router as wayback_router
from souwen.server.routes.whoami import router as whoami_router
from souwen.server.routes.youtube import router as youtube_router

router = APIRouter()

router.include_router(search_router)
router.include_router(fetch_router)
router.include_router(youtube_router)
router.include_router(wayback_router)
router.include_router(sources_router)
router.include_router(bilibili_router)
router.include_router(whoami_router)

# LLM 端点 — 始终注册，运行时检查 llm.enabled
try:
    from souwen.server.routes.deep_summarize import router as deep_summarize_router
    from souwen.server.routes.fetch_summarize import router as fetch_summarize_router
    from souwen.server.routes.summarize import router as summarize_router

    router.include_router(summarize_router)
    router.include_router(fetch_summarize_router)
    router.include_router(deep_summarize_router)
except Exception:
    import logging as _logging

    _logging.getLogger("souwen.server").warning("LLM 路由注册失败，LLM 端点不可用", exc_info=True)

__all__ = ["router", "admin_router"]
