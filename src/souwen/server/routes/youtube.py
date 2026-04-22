"""YouTube Data API 端点 — 热门 / 详情 / 字幕"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from souwen.server.auth import check_search_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.routes._common import logger
from souwen.server.schemas import (
    YouTubeTranscriptResponse,
    YouTubeTrendingResponse,
    YouTubeVideoDetailResponse,
)

router = APIRouter()


@router.get(
    "/youtube/trending",
    response_model=YouTubeTrendingResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_youtube_trending(
    region: str = Query("US", description="地区代码 (US/CN/JP/KR 等 ISO 3166-1 alpha-2)"),
    category: str = Query("", description="视频分类 ID (空=全部, 10=音乐, 20=游戏, 25=新闻)"),
    max_results: int = Query(20, ge=1, le=50, description="最大结果数"),
    timeout: float | None = Query(None, ge=1, le=60, description="端点硬超时（秒），超时返回 504"),
):
    """获取 YouTube 热门视频 — 按地区/分类。"""
    from souwen.exceptions import ConfigError, RateLimitError
    from souwen.web.youtube import YouTubeClient

    try:
        client = YouTubeClient()
        coro = client.get_trending(
            region_code=region,
            video_category_id=category or None,
            max_results=max_results,
        )
        if timeout is not None:
            results = await asyncio.wait_for(coro, timeout=timeout)
        else:
            results = await coro
        return {
            "region": region,
            "category": category,
            "results": [r.model_dump(mode="json") for r in results],
            "total": len(results),
        }
    except ConfigError as e:
        raise HTTPException(status_code=503, detail=f"YouTube API 未配置: {e}")
    except RateLimitError:
        raise HTTPException(status_code=429, detail="YouTube API 配额已用尽")
    except asyncio.TimeoutError:
        logger.warning("YouTube trending 超时: region=%s timeout=%ss", region, timeout)
        raise HTTPException(status_code=504, detail=f"请求超时（{timeout}s）")
    except Exception:
        logger.warning("YouTube trending 错误: region=%s", region, exc_info=True)
        raise


@router.get(
    "/youtube/video/{video_id}",
    response_model=YouTubeVideoDetailResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_youtube_video_detail(
    video_id: str,
    timeout: float | None = Query(None, ge=1, le=60, description="端点硬超时（秒），超时返回 504"),
):
    """获取 YouTube 视频详情 — 含统计信息（播放量/点赞/评论）。"""
    from dataclasses import asdict

    from souwen.exceptions import ConfigError, RateLimitError
    from souwen.web.youtube import YouTubeClient

    try:
        client = YouTubeClient()
        coro = client.get_video_details([video_id])
        if timeout is not None:
            results = await asyncio.wait_for(coro, timeout=timeout)
        else:
            results = await coro
        if not results:
            raise HTTPException(status_code=404, detail=f"视频 {video_id} 不存在或不可用")
        return {
            "video_ids": [video_id],
            "results": [asdict(r) for r in results],
            "total": len(results),
        }
    except HTTPException:
        raise
    except ConfigError as e:
        raise HTTPException(status_code=503, detail=f"YouTube API 未配置: {e}")
    except RateLimitError:
        raise HTTPException(status_code=429, detail="YouTube API 配额已用尽")
    except asyncio.TimeoutError:
        logger.warning("YouTube video detail 超时: video_id=%s", video_id)
        raise HTTPException(status_code=504, detail=f"请求超时（{timeout}s）")
    except Exception:
        logger.warning("YouTube video detail 错误: video_id=%s", video_id, exc_info=True)
        raise


@router.get(
    "/youtube/transcript/{video_id}",
    response_model=YouTubeTranscriptResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_youtube_transcript(
    video_id: str,
    lang: str = Query("en", description="字幕语言代码 (en/zh/ja/ko 等)"),
    timeout: float | None = Query(None, ge=1, le=60, description="端点硬超时（秒），超时返回 504"),
):
    """提取 YouTube 视频字幕 — 零配额消耗（页面抓取方式）。"""
    from souwen.exceptions import ConfigError
    from souwen.web.youtube import YouTubeClient

    try:
        client = YouTubeClient()
        coro = client.get_transcript(video_id, lang=lang)
        if timeout is not None:
            text = await asyncio.wait_for(coro, timeout=timeout)
        else:
            text = await coro
        if text is None:
            return {
                "video_id": video_id,
                "lang": lang,
                "segments": [],
                "text": "",
                "available": False,
            }
        return {
            "video_id": video_id,
            "lang": lang,
            "segments": [],
            "text": text,
            "available": True,
        }
    except ConfigError as e:
        raise HTTPException(status_code=503, detail=f"YouTube API 未配置: {e}")
    except asyncio.TimeoutError:
        logger.warning("YouTube transcript 超时: video_id=%s", video_id)
        raise HTTPException(status_code=504, detail=f"请求超时（{timeout}s）")
    except Exception:
        logger.warning("YouTube transcript 错误: video_id=%s", video_id, exc_info=True)
        raise
