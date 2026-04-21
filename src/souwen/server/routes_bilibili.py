"""Bilibili 专属 API 路由（精简版：搜索 + 抓取）

文件用途：
    暴露 BilibiliClient 的核心能力 — 视频搜索、用户搜索、专栏文章搜索
    与单条视频详情抓取，与聚合搜索（/api/v1/search/web 中的 bilibili
    引擎）互补。

    其他派生功能（评论 / 字幕 / AI 摘要 / 热门 / 排行 / 相关推荐 /
    用户信息 / 用户视频列表）属于独立的 bili-cli 项目，本仓库不再提供。

设计原则：
    - 与 routes.py 保持一致：依赖 ``rate_limit_search`` 与 ``check_search_auth``
    - 每次请求新建一个 ``BilibiliClient`` 实例并以 ``async with`` 管理生命周期
    - 将 Bilibili 异常映射为 HTTP 状态码：
        BilibiliNotFound       → 404
        BilibiliAuthRequired   → 401
        BilibiliRateLimited    → 429
        BilibiliRiskControl    → 403
        BilibiliError          → 502
    - 响应直接返回 Pydantic 模型 ``model_dump()``，保留 ``extra="allow"`` 字段

主要路由：
    GET /api/v1/bilibili/search                   — 视频搜索
    GET /api/v1/bilibili/search/users             — 用户搜索
    GET /api/v1/bilibili/search/articles          — 专栏文章搜索
    GET /api/v1/bilibili/video/{bvid}             — 视频详情

模块依赖：
    - fastapi：路由 & 依赖注入
    - souwen.web.bilibili：BilibiliClient + 异常类
    - souwen.server.auth / limiter：复用全局认证 & 限流
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from souwen.server.auth import check_search_auth
from souwen.server.limiter import rate_limit_search
from souwen.web.bilibili import BilibiliClient
from souwen.web.bilibili._errors import (
    BilibiliAuthRequired,
    BilibiliError,
    BilibiliNotFound,
    BilibiliRateLimited,
    BilibiliRiskControl,
)

logger = logging.getLogger("souwen.server")

bilibili_router = APIRouter(
    prefix="/bilibili",
    tags=["bilibili"],
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)


def _raise_for_bilibili(exc: BilibiliError) -> None:
    """将 BilibiliError 子类统一翻译为 HTTPException — 保持各端点错误处理一致。

    Args:
        exc: BilibiliClient 抛出的异常实例

    Raises:
        HTTPException: 对应的 HTTP 状态码 + 异常消息
    """
    if isinstance(exc, BilibiliNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, BilibiliAuthRequired):
        raise HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, BilibiliRateLimited):
        raise HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, BilibiliRiskControl):
        raise HTTPException(status_code=403, detail=str(exc))
    raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# 视频抓取
# ---------------------------------------------------------------------------


@bilibili_router.get("/video/{bvid}")
async def bilibili_video_details(bvid: str):
    """获取 Bilibili 视频详情（标题、UP 主、统计、标签等）。

    Raises:
        HTTPException: 404/401/429/403/502 — 见 ``_raise_for_bilibili``
    """
    try:
        async with BilibiliClient() as client:
            detail = await client.get_video_details(bvid)
            return detail.model_dump()
    except BilibiliError as e:
        _raise_for_bilibili(e)


# ---------------------------------------------------------------------------
# 搜索
# ---------------------------------------------------------------------------


@bilibili_router.get("/search")
async def bilibili_search(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    max_results: int = Query(20, ge=1, le=50, description="最大返回条数"),
    order: str = Query(
        "totalrank",
        description="排序方式：totalrank / click / pubdate / dm / stow",
    ),
):
    """按关键词搜索 Bilibili 视频（聚合接口，失败降级为空列表）。"""
    try:
        async with BilibiliClient() as client:
            response = await client.search(keyword, max_results=max_results, order=order)
            return response.model_dump(mode="json")
    except BilibiliError as e:
        _raise_for_bilibili(e)


@bilibili_router.get("/search/users")
async def bilibili_search_users(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    max_results: int = Query(20, ge=1, le=100, description="最大返回条数"),
):
    """按关键词搜索 Bilibili 用户（聚合接口，失败降级为空列表）。"""
    try:
        async with BilibiliClient() as client:
            items = await client.search_users(keyword, page=page, max_results=max_results)
            return [u.model_dump() for u in items]
    except BilibiliError as e:
        _raise_for_bilibili(e)


@bilibili_router.get("/search/articles")
async def bilibili_search_articles(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    max_results: int = Query(20, ge=1, le=50, description="最大返回条数"),
):
    """按关键词搜索 Bilibili 专栏文章（聚合接口，失败降级为空列表）。"""
    try:
        async with BilibiliClient() as client:
            results = await client.search_articles(keyword, page=page, max_results=max_results)
            return [r.model_dump() for r in results]
    except BilibiliError as e:
        _raise_for_bilibili(e)
