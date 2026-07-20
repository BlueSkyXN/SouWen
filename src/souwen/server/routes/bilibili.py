"""Bilibili 专属 API 路由（精简版：搜索 + 抓取）

暴露 BilibiliClient 的核心能力 — 视频搜索、用户搜索、专栏文章搜索
与单条视频详情抓取，与聚合搜索（/api/v1/search/web 中的 bilibili
引擎）互补。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from souwen.server.auth import check_search_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.routes._common import redact_secret_text
from souwen.server.schemas import (
    BilibiliArticleSearchResponse,
    BilibiliSearchResponse,
    BilibiliUserSearchResponse,
    BilibiliVideoDetailResponse,
)
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
    detail = redact_secret_text(str(exc)) or "Bilibili API error"
    if isinstance(exc, BilibiliNotFound):
        raise HTTPException(status_code=404, detail=detail)
    if isinstance(exc, BilibiliAuthRequired):
        raise HTTPException(status_code=401, detail=detail)
    if isinstance(exc, BilibiliRateLimited):
        raise HTTPException(status_code=429, detail=detail)
    if isinstance(exc, BilibiliRiskControl):
        raise HTTPException(status_code=403, detail=detail)
    raise HTTPException(status_code=502, detail=detail)


def _normalize_non_empty_arg(value: str, *, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{name} 不能是空字符串")
    return normalized


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: object) -> int:
    return _optional_int(value) or 0


def _text(value: object) -> str:
    return str(value) if value is not None else ""


def _extract_bvid(url: str, fallback: object) -> str:
    if fallback:
        return str(fallback)
    marker = "/video/"
    if marker not in url:
        return ""
    candidate = url.split(marker, 1)[1].split("?", 1)[0].split("/", 1)[0]
    return candidate if candidate.startswith("BV") else ""


def _format_video_search_result(result: object) -> dict[str, object]:
    """把通用 WebSearchResult 转为 Bilibili 直连搜索契约。"""
    raw = getattr(result, "raw", {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    url = _text(getattr(result, "url", ""))
    bvid = _extract_bvid(url, raw.get("bvid"))
    return {
        "bvid": bvid,
        "aid": _optional_int(raw.get("aid")),
        "title": _text(getattr(result, "title", "")),
        "author": _text(raw.get("author")),
        "mid": _optional_int(raw.get("mid")),
        "play": _int_or_zero(raw.get("play")),
        "danmaku": _int_or_zero(raw.get("video_review") or raw.get("danmaku")),
        "favorites": _optional_int(raw.get("favorites")),
        "description": _text(getattr(result, "snippet", "")),
        "duration": _text(raw.get("duration")),
        "pic": _text(raw.get("pic") or raw.get("cover")),
        "pubdate": _optional_int(raw.get("pubdate")),
        "tag": _text(raw.get("tag")) or None,
        "type": "video",
        "url": url or (f"https://www.bilibili.com/video/{bvid}" if bvid else ""),
    }


@router.get("/video/{bvid}", response_model=BilibiliVideoDetailResponse)
async def bilibili_video_details(bvid: str):
    """获取 Bilibili 视频详情（标题、UP 主、统计、标签等）。"""
    bvid = _normalize_non_empty_arg(bvid, name="bvid")
    try:
        async with BilibiliClient() as client:
            detail = await client.get_video_details(bvid)
            data = detail.model_dump(mode="json")
            return {"bvid": data.get("bvid") or bvid, "data": data}
    except BilibiliError as e:
        _raise_for_bilibili(e)


@router.get("/search", response_model=BilibiliSearchResponse)
async def bilibili_search(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    max_results: int = Query(20, ge=1, le=50, description="最大返回条数"),
    order: str = Query(
        "totalrank",
        description="排序方式：totalrank / click / pubdate / dm / stow",
    ),
):
    """按关键词搜索 Bilibili 视频（聚合接口，失败降级为空列表）。"""
    keyword = _normalize_non_empty_arg(keyword, name="keyword")
    try:
        async with BilibiliClient() as client:
            response = await client.search(keyword, max_results=max_results, order=order)
            results = [_format_video_search_result(item) for item in response.results]
            return {
                "keyword": response.query,
                "results": results,
                "total": response.total_results or len(results),
                "page": response.page,
                "page_size": max_results,
                "order": order,
            }
    except BilibiliError as e:
        _raise_for_bilibili(e)


@router.get("/search/users", response_model=BilibiliUserSearchResponse)
async def bilibili_search_users(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    max_results: int = Query(20, ge=1, le=100, description="最大返回条数"),
):
    """按关键词搜索 Bilibili 用户（聚合接口，失败降级为空列表）。"""
    keyword = _normalize_non_empty_arg(keyword, name="keyword")
    try:
        async with BilibiliClient() as client:
            items = await client.search_users(keyword, page=page, max_results=max_results)
            results = [u.model_dump(mode="json") for u in items]
            return {
                "keyword": keyword,
                "results": results,
                "total": len(results),
                "page": page,
            }
    except BilibiliError as e:
        _raise_for_bilibili(e)


@router.get("/search/articles", response_model=BilibiliArticleSearchResponse)
async def bilibili_search_articles(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    max_results: int = Query(20, ge=1, le=50, description="最大返回条数"),
):
    """按关键词搜索 Bilibili 专栏文章（聚合接口，失败降级为空列表）。"""
    keyword = _normalize_non_empty_arg(keyword, name="keyword")
    try:
        async with BilibiliClient() as client:
            results = await client.search_articles(keyword, page=page, max_results=max_results)
            payload = []
            for item in results:
                article = item.model_dump(mode="json")
                article["description"] = article.get("desc") or ""
                payload.append(article)
            return {
                "keyword": keyword,
                "results": payload,
                "total": len(payload),
                "page": page,
            }
    except BilibiliError as e:
        _raise_for_bilibili(e)
