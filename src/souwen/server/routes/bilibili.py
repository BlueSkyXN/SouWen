"""Bilibili 专属 API 路由（精简版：搜索 + 抓取）

暴露 BilibiliClient 的核心能力 — 视频搜索、用户搜索、专栏文章搜索
与单条视频详情抓取，与聚合搜索（/api/v1/search/web 中的 bilibili
引擎）互补。
"""

from __future__ import annotations

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

router = APIRouter(
    prefix="/bilibili",
    tags=["bilibili"],
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)


def _raise_for_bilibili(exc: BilibiliError) -> None:
    """将 BilibiliError 子类统一翻译为 HTTPException。"""
    if isinstance(exc, BilibiliNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, BilibiliAuthRequired):
        raise HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, BilibiliRateLimited):
        raise HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, BilibiliRiskControl):
        raise HTTPException(status_code=403, detail=str(exc))
    raise HTTPException(status_code=502, detail=str(exc))


@router.get("/video/{bvid}")
async def bilibili_video_details(bvid: str):
    """获取 Bilibili 视频详情（标题、UP 主、统计、标签等）。"""
    try:
        async with BilibiliClient() as client:
            detail = await client.get_video_details(bvid)
            return detail.model_dump()
    except BilibiliError as e:
        _raise_for_bilibili(e)


@router.get("/search")
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


@router.get("/search/users")
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


@router.get("/search/articles")
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
