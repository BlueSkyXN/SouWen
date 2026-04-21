"""Bilibili 专属 API 路由

文件用途：
    暴露 BilibiliClient 的完整能力（视频/用户/评论/字幕/AI 摘要/热门/排行/相关/用户搜索），
    与聚合搜索（/api/v1/search/web 中的 bilibili 引擎）互补。

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
    GET /api/v1/bilibili/video/{bvid}             — 视频详情
    GET /api/v1/bilibili/user/{mid}               — 用户信息
    GET /api/v1/bilibili/user/{mid}/videos        — 用户投稿视频
    GET /api/v1/bilibili/video/{bvid}/comments    — 视频评论
    GET /api/v1/bilibili/video/{bvid}/subtitles   — 视频字幕
    GET /api/v1/bilibili/video/{bvid}/ai-summary  — AI 摘要
    GET /api/v1/bilibili/popular                  — 热门视频
    GET /api/v1/bilibili/ranking                  — 排行榜
    GET /api/v1/bilibili/video/{bvid}/related     — 相关推荐
    GET /api/v1/bilibili/search/users             — 用户搜索

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
# 视频
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


@bilibili_router.get("/video/{bvid}/comments")
async def bilibili_video_comments(
    bvid: str,
    sort: int = Query(1, description="排序：0=时间, 1=点赞, 2=回复"),
    page: int = Query(1, ge=1, description="起始页码"),
    max_comments: int = Query(50, ge=1, le=500, description="最大返回评论数（硬上限）"),
):
    """获取视频评论（跨页累积，默认按点赞排序）。"""
    try:
        async with BilibiliClient() as client:
            comments = await client.get_comments(
                bvid, sort=sort, page=page, max_comments=max_comments
            )
            return [c.model_dump() for c in comments]
    except BilibiliError as e:
        _raise_for_bilibili(e)


@bilibili_router.get("/video/{bvid}/subtitles")
async def bilibili_video_subtitles(bvid: str):
    """获取视频字幕（含字幕行内容，优先返回中文字幕）。"""
    try:
        async with BilibiliClient() as client:
            subs = await client.get_subtitles(bvid)
            return [s.model_dump(by_alias=True) for s in subs]
    except BilibiliError as e:
        _raise_for_bilibili(e)


@bilibili_router.get("/video/{bvid}/ai-summary")
async def bilibili_video_ai_summary(bvid: str):
    """获取视频 AI 摘要（依赖官方 conclusion 接口，可能返回空摘要）。"""
    try:
        async with BilibiliClient() as client:
            summary = await client.get_ai_summary(bvid)
            return summary.model_dump()
    except BilibiliError as e:
        _raise_for_bilibili(e)


@bilibili_router.get("/video/{bvid}/related")
async def bilibili_video_related(bvid: str):
    """获取相关推荐视频列表（聚合接口，失败降级为空列表）。"""
    try:
        async with BilibiliClient() as client:
            related = await client.get_related(bvid)
            return [r.model_dump() for r in related]
    except BilibiliError as e:
        _raise_for_bilibili(e)


# ---------------------------------------------------------------------------
# 用户
# ---------------------------------------------------------------------------


@bilibili_router.get("/user/{mid}")
async def bilibili_user_info(mid: int):
    """获取用户信息（个人资料 + 关注/粉丝合并）。"""
    try:
        async with BilibiliClient() as client:
            info = await client.get_user_info(mid)
            return info.model_dump()
    except BilibiliError as e:
        _raise_for_bilibili(e)


@bilibili_router.get("/user/{mid}/videos")
async def bilibili_user_videos(
    mid: int,
    page: int = Query(1, ge=1, description="页码（从 1 开始）"),
    page_size: int = Query(30, ge=1, le=50, description="每页条数"),
):
    """获取用户投稿视频列表，并附带总条数。"""
    try:
        async with BilibiliClient() as client:
            items, total = await client.get_user_videos(mid, page=page, page_size=page_size)
            return {
                "items": [v.model_dump() for v in items],
                "total": total,
            }
    except BilibiliError as e:
        _raise_for_bilibili(e)


# ---------------------------------------------------------------------------
# 发现：热门 / 排行
# ---------------------------------------------------------------------------


@bilibili_router.get("/popular")
async def bilibili_popular(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=50, description="每页条数"),
):
    """获取当前热门视频（聚合接口，失败降级为空列表）。"""
    try:
        async with BilibiliClient() as client:
            items = await client.get_popular(page=page, page_size=page_size)
            return [v.model_dump() for v in items]
    except BilibiliError as e:
        _raise_for_bilibili(e)


@bilibili_router.get("/ranking")
async def bilibili_ranking(
    rid: int = Query(0, description="分区 ID，0=全站"),
    type: str = Query("all", description="排行榜类型 — all/origin/rookie"),
):
    """获取排行榜（聚合接口，失败降级为空列表）。"""
    try:
        async with BilibiliClient() as client:
            items = await client.get_ranking(rid=rid, type=type)
            return [v.model_dump() for v in items]
    except BilibiliError as e:
        _raise_for_bilibili(e)


# ---------------------------------------------------------------------------
# 搜索
# ---------------------------------------------------------------------------


@bilibili_router.get("/search")
async def bilibili_search(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    max_results: int = Query(20, ge=1, le=50, description="最大返回条数"),
):
    """按关键词搜索 Bilibili 视频（聚合接口，失败降级为空列表）。"""
    try:
        async with BilibiliClient() as client:
            results = await client.search(keyword, page=page, max_results=max_results)
            return [r.model_dump() for r in results]
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
