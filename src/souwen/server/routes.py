"""SouWen API 路由定义

文件用途：
    定义所有 API 端点（搜索、数据源配置、WARP 管理等）。
    分为两个路由器：router（搜索，宽松认证）和 admin_router（管理，强制认证）。

主要路由（按类别）：

搜索端点（public，可选认证）：
    GET /api/v1/search/paper
        - 搜索学术论文（OpenAlex、arXiv、Crossref 等多源）
        - 依赖：速率限制 + 可选认证
        - 超时支持：返回 504 Gateway Timeout

    GET /api/v1/search/patent
        - 搜索专利（Google Patents、PatentsView 等）
        - 依赖：速率限制 + 可选认证

    GET /api/v1/search/web
        - 搜索网页（DuckDuckGo、Bing、Baidu 等 21 个引擎）
        - 参数兼容性：per_page 和 max_results 别名
        - 依赖：速率限制 + 可选认证

    GET /api/v1/sources
        - 列出当前可用数据源及其配置（隐藏未配置 Key 的授权接口）

    POST /api/v1/fetch
        - 抓取网页内容（19 个提供者，详见 VALID_FETCH_PROVIDERS）
        - 依赖：速率限制 + 管理密码认证（SSRF 风险）

管理端点（强制认证）：
    GET /api/v1/admin/config
        - 查看当前配置（敏感字段脱敏）

    POST /api/v1/admin/config/reload
        - 重新加载 YAML + .env 配置

    GET /api/v1/admin/doctor
        - 数据源健康检查（连接性测试）

    GET /api/v1/admin/ping
        - 轻量级管理端存活探测

数据源频道配置端点：
    GET /api/v1/admin/sources/config
        - 查看所有数据源的频道配置

    GET /api/v1/admin/sources/config/{source_name}
        - 查看单个数据源配置

    PUT /api/v1/admin/sources/config/{source_name}
        - 更新数据源配置（运行时，JSON 请求体避免 API Key 泄露）

HTTP 后端配置（兼容旧版）：
    GET /api/v1/admin/http-backend
        - 查看当前 HTTP 后端配置

    PUT /api/v1/admin/http-backend
        - 更新 HTTP 后端（curl_cffi / httpx / auto）

WARP 代理管理：
    GET /api/v1/admin/warp
        - 获取 WARP 代理状态

    POST /api/v1/admin/warp/enable
        - 启用 WARP 代理（auto / wireproxy / kernel 模式）

    POST /api/v1/admin/warp/disable
        - 禁用 WARP 代理

全局代理配置：
    GET /api/v1/admin/proxy
        - 查看全局代理和代理池配置

    PUT /api/v1/admin/proxy
        - 更新全局代理/代理池（JSON 请求体）

主要类/函数：
    _is_secret_field(name: str) -> bool
        - 判断字段是否包含敏感信息（key、secret、token、password）
        - 用于脱敏配置输出

认证策略：
    - search/* 端点：check_search_auth（密码未配置时放行）
    - admin/* 端点：require_auth（强制认证）

模块依赖：
    - fastapi：路由和依赖注入
    - souwen.search：论文、专利、网页搜索
    - souwen.config：配置管理
    - souwen.doctor：数据源健康检查
    - souwen.server.warp：WARP 代理管理
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query, HTTPException

from souwen.server.auth import check_search_auth, require_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.schemas import (
    ConfigReloadResponse,
    DoctorResponse,
    FetchRequest,
    HttpBackendResponse,
    ProxyConfigResponse,
    SearchImagesResponse,
    SearchPaperResponse,
    SearchPatentResponse,
    SearchVideosResponse,
    SearchWebResponse,
    UpdateProxyConfigRequest,
    UpdateSourceConfigRequest,
    WaybackAvailabilityResponse,
    WaybackCDXApiResponse,
    WaybackSaveRequest,
    WaybackSaveResponse,
    YouTubeTranscriptResponse,
    YouTubeTrendingResponse,
    YouTubeVideoDetailResponse,
)

logger = logging.getLogger("souwen.server")

router = APIRouter()

# ---------------------------------------------------------------------------
# 搜索端点 — 受 check_search_auth 保护（有密码时需认证，无密码时放行）
# ---------------------------------------------------------------------------


@router.get(
    "/search/paper",
    response_model=SearchPaperResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_paper(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str = Query("openalex,arxiv", description="数据源，逗号分隔"),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索学术论文 — 支持多数据源并联查询

    支持的数据源：openalex, arxiv, crossref, dblp, core, pubmed, unpaywall 等

    超时处理：
    - timeout 为 None 时无限等待
    - 若超时，返回 504 Gateway Timeout
    - 支持部分失败：某些源超时/失败时，已成功的源结果仍被返回

    返回格式：
        {
            "query": "搜索关键词",
            "sources": ["openalex", "arxiv"],
            "results": [...],
            "total": 结果总数,
            "meta": {
                "requested": 请求的源,
                "succeeded": 成功的源,
                "failed": 失败的源
            }
        }

    Raises:
        HTTPException：502 当所有数据源均失败，504 当全局超时
    """
    from souwen.exceptions import SouWenError
    from souwen.search import search_papers

    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    try:
        coro = search_papers(q, sources=source_list, per_page=per_page)
        if timeout is not None:
            results = await asyncio.wait_for(coro, timeout=timeout)
        else:
            results = await coro
        succeeded = [r.source.value for r in results]
        return {
            "query": q,
            "sources": source_list,
            "results": [r.model_dump(mode="json") for r in results],
            "total": sum(len(r.results) for r in results),
            "meta": {
                "requested": source_list,
                "succeeded": succeeded,
                "failed": [s for s in source_list if s not in succeeded],
            },
        }
    except asyncio.TimeoutError:
        logger.warning("论文搜索超时: q=%s timeout=%ss", q, timeout)
        raise HTTPException(status_code=504, detail=f"搜索超时（{timeout}s）")
    except SouWenError:
        logger.exception("论文搜索上游失败: q=%s sources=%s", q, source_list)
        raise HTTPException(status_code=502, detail="所有上游数据源均不可用")
    except Exception:
        logger.warning("论文搜索内部错误: q=%s", q, exc_info=True)
        raise


@router.get(
    "/search/patent",
    response_model=SearchPatentResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_patent(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str = Query("google_patents", description="数据源，逗号分隔"),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索专利 — 支持多数据源并联查询

    支持的数据源：google_patents, patentsview, pqai, epo_ops, uspto 等

    超时和失败处理同 /search/paper

    Raises:
        HTTPException：502 当所有数据源均失败，504 当全局超时
    """
    from souwen.exceptions import SouWenError
    from souwen.search import search_patents

    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    try:
        coro = search_patents(q, sources=source_list, per_page=per_page)
        if timeout is not None:
            results = await asyncio.wait_for(coro, timeout=timeout)
        else:
            results = await coro
        succeeded = [r.source.value for r in results]
        return {
            "query": q,
            "sources": source_list,
            "results": [r.model_dump(mode="json") for r in results],
            "total": sum(len(r.results) for r in results),
            "meta": {
                "requested": source_list,
                "succeeded": succeeded,
                "failed": [s for s in source_list if s not in succeeded],
            },
        }
    except asyncio.TimeoutError:
        logger.warning("专利搜索超时: q=%s timeout=%ss", q, timeout)
        raise HTTPException(status_code=504, detail=f"搜索超时（{timeout}s）")
    except SouWenError:
        logger.exception("专利搜索上游失败: q=%s sources=%s", q, source_list)
        raise HTTPException(status_code=502, detail="所有上游数据源均不可用")
    except Exception:
        logger.warning("专利搜索内部错误: q=%s", q, exc_info=True)
        raise


@router.get(
    "/search/web",
    response_model=SearchWebResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_web(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    engines: str = Query("duckduckgo,bing", description="搜索引擎，逗号分隔"),
    per_page: int = Query(
        10, ge=1, le=50, alias="per_page", description="每引擎最大结果数（别名: max_results）"
    ),
    max_results: int | None = Query(None, ge=1, le=50, description="兼容旧版：每引擎最大结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索网页 — 支持 21+ 搜索引擎

    支持的引擎：duckduckgo, bing, google, baidu, yahoo, brave 等

    参数兼容性：
    - per_page 和 max_results 均可指定每引擎结果数
    - max_results 优先级高于 per_page（向后兼容）

    返回结构同 /search/paper，但 engines 代替 sources

    Raises:
        HTTPException：502 当所有引擎均失败，504 当全局超时
    """
    from souwen.exceptions import SouWenError
    from souwen.web.search import web_search

    engine_list = [e.strip() for e in engines.split(",") if e.strip()]
    effective = max_results if max_results is not None else per_page
    try:
        coro = web_search(q, engines=engine_list, max_results_per_engine=effective)
        if timeout is not None:
            resp = await asyncio.wait_for(coro, timeout=timeout)
        else:
            resp = await coro
        results_dump = [r.model_dump(mode="json") for r in resp.results]
        succeeded = sorted({r.engine for r in resp.results})
        failed = [e for e in engine_list if e not in succeeded]
        return {
            "query": resp.query,
            "engines": engine_list,
            "results": results_dump,
            "total": len(results_dump),
            "meta": {
                "requested": engine_list,
                "succeeded": succeeded,
                "failed": failed,
            },
        }
    except asyncio.TimeoutError:
        logger.warning("网页搜索超时: q=%s timeout=%ss", q, timeout)
        raise HTTPException(status_code=504, detail=f"搜索超时（{timeout}s）")
    except SouWenError:
        logger.exception("网页搜索上游失败: q=%s engines=%s", q, engine_list)
        raise HTTPException(status_code=502, detail="所有上游搜索引擎均不可用")
    except Exception:
        logger.warning("网页搜索内部错误: q=%s", q, exc_info=True)
        raise


# ---------------------------------------------------------------------------
# 多媒体搜索 — 图片 / 视频（DuckDuckGo）
# ---------------------------------------------------------------------------


@router.get(
    "/search/images",
    response_model=SearchImagesResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_images(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    max_results: int = Query(20, ge=1, le=100, description="最大结果数"),
    region: str = Query("wt-wt", description="区域 (wt-wt=全球, cn-zh=中国)"),
    safesearch: str = Query("moderate", description="安全搜索 (on/moderate/off)"),
    timeout: float | None = Query(None, ge=1, le=120, description="端点硬超时（秒），超时返回 504"),
):
    """搜索图片 — DuckDuckGo Images

    支持 region/safesearch 等基础过滤；如需 size/color/license 过滤请使用底层客户端。

    Raises:
        HTTPException：504 超时，502 引擎不可用
    """
    from souwen.web.ddg_images import DuckDuckGoImagesClient

    try:
        client = DuckDuckGoImagesClient()
        coro = client.search(query=q, max_results=max_results, region=region, safesearch=safesearch)
        if timeout is not None:
            resp = await asyncio.wait_for(coro, timeout=timeout)
        else:
            resp = await coro
        return {
            "query": resp.query,
            "results": [r.model_dump(mode="json") for r in resp.results],
            "total": len(resp.results),
            "meta": {
                "requested": ["duckduckgo_images"],
                "succeeded": ["duckduckgo_images"],
                "failed": [],
            },
        }
    except asyncio.TimeoutError:
        logger.warning("图片搜索超时: q=%s timeout=%ss", q, timeout)
        raise HTTPException(status_code=504, detail=f"图片搜索超时（{timeout}s）")
    except Exception:
        logger.warning("图片搜索内部错误: q=%s", q, exc_info=True)
        raise HTTPException(status_code=502, detail="图片搜索引擎不可用")


@router.get(
    "/search/videos",
    response_model=SearchVideosResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_videos(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    max_results: int = Query(20, ge=1, le=100, description="最大结果数"),
    region: str = Query("wt-wt", description="区域"),
    safesearch: str = Query("moderate", description="安全搜索 (on/moderate/off)"),
    timeout: float | None = Query(None, ge=1, le=120, description="端点硬超时（秒），超时返回 504"),
):
    """搜索视频 — DuckDuckGo Videos

    返回视频元信息（标题、时长、发布者、缩略图、嵌入 URL 等）。

    Raises:
        HTTPException：504 超时，502 引擎不可用
    """
    from souwen.web.ddg_videos import DuckDuckGoVideosClient

    try:
        client = DuckDuckGoVideosClient()
        coro = client.search(query=q, max_results=max_results, region=region, safesearch=safesearch)
        if timeout is not None:
            resp = await asyncio.wait_for(coro, timeout=timeout)
        else:
            resp = await coro
        return {
            "query": resp.query,
            "results": [r.model_dump(mode="json") for r in resp.results],
            "total": len(resp.results),
            "meta": {
                "requested": ["duckduckgo_videos"],
                "succeeded": ["duckduckgo_videos"],
                "failed": [],
            },
        }
    except asyncio.TimeoutError:
        logger.warning("视频搜索超时: q=%s timeout=%ss", q, timeout)
        raise HTTPException(status_code=504, detail=f"视频搜索超时（{timeout}s）")
    except Exception:
        logger.warning("视频搜索内部错误: q=%s", q, exc_info=True)
        raise HTTPException(status_code=502, detail="视频搜索引擎不可用")


# ---------------------------------------------------------------------------
# YouTube Data API — 热门 / 详情 / 字幕
# ---------------------------------------------------------------------------


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
    """获取 YouTube 热门视频 — 按地区/分类

    需要配置 YOUTUBE_API_KEY；缺失时返回 503。

    Raises:
        HTTPException：503 未配置 Key，429 配额耗尽，504 超时
    """
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
    """获取 YouTube 视频详情 — 含统计信息（播放量/点赞/评论）

    Raises:
        HTTPException：404 视频不存在，503 未配置 Key，429 配额耗尽，504 超时
    """
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
    """提取 YouTube 视频字幕 — 零配额消耗（页面抓取方式）

    返回纯文本字幕（按段落换行）；构造 YouTubeClient 仍要求配置 API Key。

    Raises:
        HTTPException：503 未配置 Key，504 超时
    """
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


# ---------------------------------------------------------------------------
# Wayback Machine — 公开查询（CDX / Availability）
# ---------------------------------------------------------------------------


@router.get(
    "/wayback/cdx",
    response_model=WaybackCDXApiResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_wayback_cdx(
    url: str = Query(..., description="查询 URL (支持通配符 *)"),
    from_date: str | None = Query(None, alias="from", description="起始日期 (YYYYMMDD)"),
    to_date: str | None = Query(None, alias="to", description="结束日期 (YYYYMMDD)"),
    limit: int = Query(100, ge=1, le=10000, description="最大快照数"),
    filter_status: int | None = Query(None, description="HTTP 状态码过滤 (如 200)"),
    collapse: str | None = Query(None, description="去重规则 (如 timestamp:8 按天去重)"),
    timeout: float | None = Query(None, ge=1, le=120, description="端点硬超时（秒），超时返回 504"),
):
    """查询 Wayback Machine CDX — URL 历史快照列表

    Raises:
        HTTPException：504 超时
    """
    from souwen.web.wayback import WaybackClient

    inner_timeout = timeout or 60.0
    try:
        client = WaybackClient()
        coro = client.query_snapshots(
            url=url,
            from_date=from_date,
            to_date=to_date,
            filter_status=[filter_status] if filter_status is not None else None,
            limit=limit,
            collapse=collapse,
            timeout=inner_timeout,
        )
        if timeout is not None:
            resp = await asyncio.wait_for(coro, timeout=timeout + 5)
        else:
            resp = await coro
        return {
            "url": url,
            "snapshots": [s.model_dump(mode="json") for s in resp.snapshots],
            "total": resp.total,
        }
    except asyncio.TimeoutError:
        logger.warning("Wayback CDX 超时: url=%s timeout=%ss", url, timeout)
        raise HTTPException(status_code=504, detail=f"CDX 查询超时（{timeout}s）")
    except Exception:
        logger.warning("Wayback CDX 错误: url=%s", url, exc_info=True)
        raise


@router.get(
    "/wayback/check",
    response_model=WaybackAvailabilityResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_wayback_check(
    url: str = Query(..., description="目标 URL"),
    timestamp: str | None = Query(None, description="目标时间戳 (YYYYMMDD 或 YYYYMMDDHHMMSS)"),
    timeout: float | None = Query(None, ge=1, le=60, description="端点硬超时（秒），超时返回 504"),
):
    """检查 URL 在 Wayback Machine 中的可用性

    Raises:
        HTTPException：504 超时
    """
    from souwen.web.wayback import WaybackClient

    inner_timeout = timeout or 30.0
    try:
        client = WaybackClient()
        coro = client.check_availability(url=url, timestamp=timestamp, timeout=inner_timeout)
        if timeout is not None:
            resp = await asyncio.wait_for(coro, timeout=timeout + 5)
        else:
            resp = await coro
        return {
            "url": url,
            "available": resp.available,
            "snapshot_url": resp.snapshot_url,
            "timestamp": resp.timestamp,
            "status": resp.status_code,
        }
    except asyncio.TimeoutError:
        logger.warning("Wayback availability 超时: url=%s timeout=%ss", url, timeout)
        raise HTTPException(status_code=504, detail=f"可用性检查超时（{timeout}s）")
    except Exception:
        logger.warning("Wayback availability 错误: url=%s", url, exc_info=True)
        raise


@router.get("/sources", dependencies=[Depends(check_search_auth)])
async def list_sources():
    """列出当前可用数据源 — 按类别分组

    需要 API Key 或自托管配置但未设置的源不会返回，
    确保前端搜索页只展示真正可用的通道。

    返回结构：
        {
            "paper": [...],
            "patent": [...],
            "general": [...],
            "professional": [...],
            "social": [...],
            "developer": [...],
            "wiki": [...],
            "video": [...]
        }
    """
    from souwen.config import get_config
    from souwen.models import ALL_SOURCES
    from souwen.source_registry import get_source

    cfg = get_config()

    def _is_usable(name: str, needs_key: bool) -> bool:
        """判断源是否可用：不需要密钥的直接可用，需要密钥的检查配置"""
        if not needs_key:
            return True
        meta = get_source(name)
        if meta is None or meta.config_field is None:
            return True
        # self_hosted 类需要 base_url，检查 resolve_base_url 或直接读字段
        if meta.integration_type == "self_hosted":
            return bool(cfg.resolve_base_url(name) or getattr(cfg, meta.config_field, None))
        # official_api 类需要 api_key
        return bool(cfg.resolve_api_key(name, meta.config_field))

    return {
        category: [
            {"name": name, "needs_key": needs_key, "description": desc}
            for name, needs_key, desc in entries
            if _is_usable(name, needs_key)
        ]
        for category, entries in ALL_SOURCES.items()
    }


# ---------------------------------------------------------------------------
# 内容抓取端点 — 需要管理密码认证（比搜索更重，SSRF 风险）
# ---------------------------------------------------------------------------

VALID_FETCH_PROVIDERS = {
    "builtin",
    "jina_reader",
    "tavily",
    "firecrawl",
    "exa",
    "crawl4ai",
    "scrapfly",
    "diffbot",
    "scrapingbee",
    "zenrows",
    "scraperapi",
    "apify",
    "cloudflare",
    "wayback",
    "newspaper",
    "readability",
    "mcp",
    "site_crawler",
    "deepwiki",
}


@router.post(
    "/fetch",
    dependencies=[Depends(rate_limit_search), Depends(require_auth)],
)
async def fetch_content_endpoint(body: FetchRequest):
    """抓取网页内容 — 支持 19 个提供者

    通过指定的提供者抓取 URL 列表内容，返回提取的 Markdown/文本。
    默认使用 builtin（内置，httpx/curl_cffi + trafilatura，零配置）。
    全部提供者：builtin / jina_reader / tavily / firecrawl / exa /
    crawl4ai / scrapfly / diffbot / scrapingbee / zenrows /
    scraperapi / apify / cloudflare / wayback / newspaper / readability /
    mcp / site_crawler / deepwiki

    需要管理密码认证（比搜索端点更重，有 SSRF 风险）。

    Raises:
        HTTPException：400 无效提供者，502 抓取全部失败，504 超时
    """
    from souwen.web.fetch import fetch_content

    if body.provider not in VALID_FETCH_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"无效提供者: {body.provider}，可选: {', '.join(sorted(VALID_FETCH_PROVIDERS))}",
        )

    try:
        resp = await asyncio.wait_for(
            fetch_content(
                urls=body.urls,
                providers=[body.provider],
                timeout=body.timeout,
            ),
            timeout=body.timeout + 15,  # 给聚合层留缓冲
        )
        return {
            "urls": resp.urls,
            "results": [r.model_dump(mode="json") for r in resp.results],
            "total": resp.total,
            "total_ok": resp.total_ok,
            "total_failed": resp.total_failed,
            "provider": resp.provider,
            "meta": resp.meta,
        }
    except asyncio.TimeoutError:
        logger.warning("内容抓取超时: provider=%s urls=%d", body.provider, len(body.urls))
        raise HTTPException(status_code=504, detail=f"抓取超时（{body.timeout}s）")
    except Exception:
        logger.warning("内容抓取内部错误: provider=%s", body.provider, exc_info=True)
        raise


# ---------------------------------------------------------------------------
# 管理端点 — 始终需要 api_password 认证
# ---------------------------------------------------------------------------
admin_router = APIRouter(dependencies=[Depends(require_auth)])

_SECRET_KEYWORDS = {"key", "secret", "token", "password"}


def _is_secret_field(name: str) -> bool:
    """判断字段名是否包含敏感信息 — 用于脱敏配置输出

    检查字段名中是否包含 key、secret、token、password 关键词。

    Args:
        name: 字段名

    Returns:
        True 当字段名包含敏感词，False 否则
    """
    return any(kw in name for kw in _SECRET_KEYWORDS)


@admin_router.get("/config")
async def get_config_view():
    """查看当前配置（敏感字段脱敏） — 管理端点

    返回所有配置项，但将包含 key/secret/token/password 的字段值替换为 "***"。

    Returns:
        dict：配置项名 → 配置值（敏感项脱敏）
    """
    from souwen.config import SouWenConfig, get_config

    cfg = get_config()
    result = {}
    for field_name in SouWenConfig.model_fields:
        val = getattr(cfg, field_name)
        if _is_secret_field(field_name) and val is not None:
            result[field_name] = "***"
        else:
            result[field_name] = val
    return result


@admin_router.post("/config/reload", response_model=ConfigReloadResponse)
async def reload_config_endpoint():
    """重新加载配置 — 从 YAML + .env 重新读取

    返回重新加载后的配置状态。

    Returns:
        {"status": "ok", "password_set": bool}
    """
    from souwen.config import reload_config

    cfg = reload_config()
    return {
        "status": "ok",
        "password_set": cfg.effective_admin_password is not None,
    }


@admin_router.get("/doctor", response_model=DoctorResponse)
async def doctor_check():
    """数据源健康检查 — 测试所有数据源连接性

    对每个已启用的数据源执行连接性测试。

    Returns:
        {
            "total": 总数源数,
            "ok": 状态正常的数源数,
            "sources": [
                {"name": "source", "status": "ok|error", "message": "..."},
                ...
            ]
        }
    """
    from souwen.doctor import check_all

    results = check_all()
    ok_count = sum(1 for r in results if r["status"] == "ok")
    return {
        "total": len(results),
        "ok": ok_count,
        "sources": results,
    }


@admin_router.get("/ping")
async def admin_ping():
    """轻量级管理端存活探测 — 完全通过认证后返回

    与 /health 不同，此端点需要通过 require_auth 认证。
    用于确认管理 API 本身可用，但不暴露配置信息。

    Returns:
        {"status": "ok"}
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 数据源频道配置
# ---------------------------------------------------------------------------


@admin_router.get("/sources/config")
async def get_sources_config():
    """查看所有数据源的频道配置 — 包含启用状态、API Key、代理等

    返回每个数据源的详细配置，包括是否启用、代理设置、自定义头等。
    API Key 本身不暴露，仅指示是否存在（has_api_key: bool）。

    Returns:
        {
            "openalex": {
                "enabled": bool,
                "proxy": str|null,
                "http_backend": str,
                "base_url": str|null,
                "has_api_key": bool,
                "headers": dict,
                "params": dict,
                "category": str,
                "integration_type": str,
                "description": str
            },
            ...
        }
    """
    from souwen.config import get_config
    from souwen.source_registry import get_all_sources

    cfg = get_config()
    all_sources = get_all_sources()
    result: dict = {}
    for name, meta in all_sources.items():
        sc = cfg.get_source_config(name)
        entry: dict = {
            "enabled": sc.enabled,
            "proxy": sc.proxy,
            "http_backend": sc.http_backend,
            "base_url": sc.base_url,
            "has_api_key": bool(cfg.resolve_api_key(name, meta.config_field)),
            "headers": sc.headers,
            "params": sc.params,
            "category": meta.category,
            "integration_type": meta.integration_type,
            "description": meta.description,
        }
        result[name] = entry
    return result


@admin_router.get("/sources/config/{source_name}")
async def get_source_config(source_name: str):
    """查看单个数据源的频道配置

    Args:
        source_name: 数据源名称（如 "openalex"）

    Returns:
        同 get_sources_config 中的单个源配置

    Raises:
        HTTPException：404 当数据源不存在
    """
    from souwen.config import get_config
    from souwen.source_registry import get_source

    meta = get_source(source_name)
    if meta is None:
        raise HTTPException(404, f"未知数据源: {source_name}")

    cfg = get_config()
    sc = cfg.get_source_config(source_name)
    return {
        "name": source_name,
        "enabled": sc.enabled,
        "proxy": sc.proxy,
        "http_backend": sc.http_backend,
        "base_url": sc.base_url,
        "has_api_key": bool(cfg.resolve_api_key(source_name, meta.config_field)),
        "headers": sc.headers,
        "params": sc.params,
        "category": meta.category,
        "integration_type": meta.integration_type,
        "description": meta.description,
    }


@admin_router.put("/sources/config/{source_name}")
async def update_source_config(
    source_name: str,
    req: UpdateSourceConfigRequest,
):
    """更新单个数据源的频道配置（运行时生效）

    使用 JSON 请求体传递参数（而非 URL Query），避免 API Key 泄露到日志中。

    参数：
        enabled: 是否启用该数据源
        proxy: HTTP/SOCKS 代理 URL
        http_backend: 优先级高于全局 default_http_backend（auto/curl_cffi/httpx）
        base_url: 自定义数据源基础 URL
        api_key: API Key（支持对源进行个性化配置）

    更新仅在内存中生效，重启后需通过 YAML/环境变量持久化。

    Args:
        source_name: 数据源名称
        req: UpdateSourceConfigRequest 请求体

    Returns:
        {"status": "ok", "source": "source_name"}

    Raises:
        HTTPException：404 当数据源不存在，400 当配置参数无效
    """
    from souwen.config import SourceChannelConfig, _validate_proxy_url, get_config
    from souwen.source_registry import is_known_source

    if not is_known_source(source_name):
        raise HTTPException(404, f"未知数据源: {source_name}")

    _VALID_BACKENDS = {"auto", "curl_cffi", "httpx"}
    if req.http_backend is not None and req.http_backend not in _VALID_BACKENDS:
        raise HTTPException(400, f"无效的 http_backend: {req.http_backend}")

    cfg = get_config()
    sc = cfg.sources.get(source_name, SourceChannelConfig())

    if req.enabled is not None:
        sc.enabled = req.enabled
    if req.proxy is not None:
        # 特殊值（inherit/none/warp）不走 URL 校验
        _PROXY_KEYWORDS = {"inherit", "none", "warp"}
        if req.proxy.strip().lower() not in _PROXY_KEYWORDS and req.proxy.strip():
            try:
                _validate_proxy_url(req.proxy)
            except ValueError as e:
                raise HTTPException(422, f"代理 URL 无效: {e}")
        sc.proxy = req.proxy
    if req.http_backend is not None:
        sc.http_backend = req.http_backend
    if req.base_url is not None:
        if req.base_url:
            _parsed = urlparse(req.base_url)
            if _parsed.scheme not in ("http", "https") or not _parsed.hostname:
                raise HTTPException(
                    status_code=422, detail=f"base_url 必须为 http/https URL: {req.base_url}"
                )
        sc.base_url = req.base_url if req.base_url else None
    if req.api_key is not None:
        sc.api_key = req.api_key if req.api_key else None

    cfg.sources[source_name] = sc
    return {"status": "ok", "source": source_name}


# ---------------------------------------------------------------------------
# 全局代理配置
# ---------------------------------------------------------------------------


@admin_router.get("/proxy", response_model=ProxyConfigResponse)
async def get_proxy_config():
    """查看全局代理配置

    Returns:
        {
            "proxy": "socks5://127.0.0.1:1080" | null,
            "proxy_pool": [...],
            "socks_supported": true/false
        }
    """
    from souwen.config import get_config

    cfg = get_config()
    socks_ok = False
    try:
        import socksio  # noqa: F401

        socks_ok = True
    except ImportError:
        pass
    return {
        "proxy": cfg.proxy,
        "proxy_pool": list(cfg.proxy_pool),
        "socks_supported": socks_ok,
    }


@admin_router.put("/proxy")
async def update_proxy_config(req: UpdateProxyConfigRequest):
    """更新全局代理配置（运行时生效）

    使用 JSON 请求体避免代理 URL 中的凭据泄露到日志中。

    Args:
        req: UpdateProxyConfigRequest 请求体

    Returns:
        {"status": "ok", "proxy": ..., "proxy_pool": [...]}

    Raises:
        HTTPException: 422 当代理 URL 无效
    """
    from souwen.config import _validate_proxy_url, get_config

    cfg = get_config()

    if req.proxy is not None:
        if req.proxy:
            try:
                _validate_proxy_url(req.proxy)
            except ValueError as e:
                raise HTTPException(422, str(e))
            parsed = urlparse(req.proxy)
            if parsed.scheme.lower() in ("socks5", "socks5h", "socks4", "socks4a"):
                try:
                    import socksio  # noqa: F401
                except ImportError:
                    raise HTTPException(
                        422,
                        f"SOCKS 代理需要安装 httpx[socks] (socksio): {req.proxy}",
                    )
            cfg.proxy = req.proxy
        else:
            cfg.proxy = None

    if req.proxy_pool is not None:
        validated = []
        for url in req.proxy_pool:
            try:
                v = _validate_proxy_url(url)
                if v:
                    validated.append(v)
            except ValueError as e:
                raise HTTPException(422, f"代理池 URL 无效: {e}")
        for url in validated:
            parsed = urlparse(url)
            if parsed.scheme.lower() in ("socks5", "socks5h", "socks4", "socks4a"):
                try:
                    import socksio  # noqa: F401
                except ImportError:
                    raise HTTPException(
                        422,
                        f"代理池中含 SOCKS 代理但未安装 httpx[socks] (socksio): {url}",
                    )
        cfg.proxy_pool = validated

    return {
        "status": "ok",
        "proxy": cfg.proxy,
        "proxy_pool": list(cfg.proxy_pool),
    }


# ---------------------------------------------------------------------------
# HTTP 后端配置（旧版兼容）
# ---------------------------------------------------------------------------

# 使用 BaseScraper 的引擎名称列表（可配置 HTTP 后端）
_SCRAPER_ENGINES = [
    "duckduckgo",
    "yahoo",
    "brave",
    "google",
    "bing",
    "startpage",
    "baidu",
    "mojeek",
    "yandex",
    "google_patents",
]


@admin_router.get("/http-backend", response_model=HttpBackendResponse)
async def get_http_backend():
    """查看 HTTP 后端配置

    显示全局默认后端和各数据源的个性化覆盖配置。
    还指示 curl_cffi 库是否可用。

    Returns:
        {
            "default": "auto|curl_cffi|httpx",
            "overrides": {"engine": "backend", ...},
            "curl_cffi_available": bool
        }
    """
    from souwen.config import get_config
    from souwen.scraper.base import _HAS_CURL_CFFI

    cfg = get_config()
    return {
        "default": cfg.default_http_backend,
        "overrides": cfg.http_backend,
        "curl_cffi_available": _HAS_CURL_CFFI,
    }


@admin_router.put("/http-backend")
async def update_http_backend(
    default: str | None = Query(None, description="全局默认: auto | curl_cffi | httpx"),
    source: str | None = Query(None, description="要覆盖的源名称"),
    backend: str | None = Query(None, description="后端: auto | curl_cffi | httpx"),
):
    """更新 HTTP 后端配置（运行时生效）

    支持两种更新模式：
        1. 更新全局默认后端：?default=curl_cffi
        2. 为特定数据源设置覆盖：?source=duckduckgo&backend=httpx
           - 若 backend=auto，移除该源的覆盖（回退到全局默认）

    Args:
        default: 新的全局默认后端
        source: 要覆盖的数据源名称
        backend: 该数据源使用的后端

    Returns:
        {
            "status": "ok",
            "default": 新的全局默认,
            "overrides": 更新后的覆盖配置
        }

    Raises:
        HTTPException：400 当后端或数据源无效
    """
    from souwen.config import get_config

    _VALID = {"auto", "curl_cffi", "httpx"}
    cfg = get_config()

    if default is not None:
        if default not in _VALID:
            raise HTTPException(400, f"无效的默认后端: {default}，可选: {', '.join(_VALID)}")
        cfg.default_http_backend = default

    if source is not None and backend is not None:
        if backend not in _VALID:
            raise HTTPException(400, f"无效的后端: {backend}，可选: {', '.join(_VALID)}")
        if source not in _SCRAPER_ENGINES:
            raise HTTPException(
                400,
                f"未知的爬虫源: {source}，可选: {', '.join(_SCRAPER_ENGINES)}",
            )
        if backend == "auto":
            cfg.http_backend.pop(source, None)
        else:
            cfg.http_backend[source] = backend

    return {
        "status": "ok",
        "default": cfg.default_http_backend,
        "overrides": cfg.http_backend,
    }


# ---------------------------------------------------------------------------
# WARP 代理管理
# ---------------------------------------------------------------------------


@admin_router.get("/warp")
async def warp_status():
    """获取 WARP 代理状态 — 包括模式、IP、PID 等

    返回完整的 WARP 状态信息，用于管理 UI 或监控系统。

    Returns:
        {
            "status": "disabled|starting|enabled|stopping|error",
            "mode": "auto|wireproxy|kernel",
            "owner": "none|shell|python",
            "socks_port": int,
            "ip": str,
            "pid": int,
            "interface": str|null,
            "last_error": str,
            "available_modes": {"wireproxy": bool, "kernel": bool}
        }
    """
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    return mgr.get_status()


@admin_router.post("/warp/enable")
async def warp_enable(
    mode: str = Query("auto", description="模式: auto | wireproxy | kernel"),
    socks_port: int = Query(1080, ge=1, le=65535, description="SOCKS5 端口"),
    endpoint: str | None = Query(None, description="自定义 WARP Endpoint"),
):
    """启用 WARP 代理 — 支持 auto、wireproxy、kernel 三种模式

    模式选择：
        - auto：自动检测最优可用模式（kernel > wireproxy）
        - wireproxy：用户态代理（不需要 root，但性能略低）
        - kernel：内核 WireGuard + microsocks（需要 root 和 /dev/net/tun）

    Args:
        mode: 启动模式
        socks_port: 本地 SOCKS5 监听端口
        endpoint: 自定义 WARP Endpoint URL（可选）

    Returns:
        {"ok": true, "mode": "wireproxy|kernel", "ip": "IP 地址"}
        或 {"ok": false, "error": "错误信息"}
    """
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    result = await mgr.enable(mode=mode, socks_port=socks_port, endpoint=endpoint)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@admin_router.post("/warp/disable")
async def warp_disable():
    """禁用 WARP 代理 — 清理进程和网络配置

    内部逻辑：
    1. 终止代理进程（wireproxy 或 microsocks）
    2. 对 kernel 模式拆除 WireGuard 接口
    3. 清空代理配置，重载 SouWen 配置

    Returns:
        {"ok": true, "message": "WARP 已关闭"}
        或 {"ok": false, "error": "错误信息"}
    """
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    result = await mgr.disable()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Wayback Machine — 写入操作（管理认证）
# ---------------------------------------------------------------------------


@admin_router.post("/wayback/save", response_model=WaybackSaveResponse)
async def api_wayback_save(body: WaybackSaveRequest):
    """触发 Wayback Machine 立即存档 — 需要管理认证

    Internet Archive 的 Save Page Now 受全局速率限制约束（约 15 次/分钟），
    存档完成可能需要 30-120 秒，请合理设置 timeout。

    Raises:
        HTTPException：504 超时
    """
    from souwen.web.wayback import WaybackClient

    try:
        client = WaybackClient()
        resp = await asyncio.wait_for(
            client.save_page(url=body.url, timeout=body.timeout),
            timeout=body.timeout + 15,
        )
        return {
            "url": body.url,
            "success": resp.success,
            "snapshot_url": resp.snapshot_url,
            "timestamp": resp.timestamp,
            "error": resp.error,
        }
    except asyncio.TimeoutError:
        logger.warning("Wayback save 超时: url=%s timeout=%ss", body.url, body.timeout)
        raise HTTPException(status_code=504, detail=f"存档超时（{body.timeout}s）")
    except Exception:
        logger.warning("Wayback save 错误: url=%s", body.url, exc_info=True)
        raise
