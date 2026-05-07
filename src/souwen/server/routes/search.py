"""搜索端点 — 论文 / 专利 / 网页 / 图片 / 视频"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from souwen.registry import defaults_for
from souwen.server.auth import check_search_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.routes._common import logger
from souwen.server.schemas import (
    SearchImagesResponse,
    SearchPaperResponse,
    SearchPatentResponse,
    SearchVideosResponse,
    SearchWebResponse,
)

router = APIRouter()
_DEFAULT_PAPER_SOURCES = defaults_for("paper", "search")
_DEFAULT_PAPER_SOURCES_LABEL = ",".join(_DEFAULT_PAPER_SOURCES)


@router.get(
    "/search/paper",
    response_model=SearchPaperResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_paper(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str | None = Query(
        None,
        description=f"数据源，逗号分隔；默认 {_DEFAULT_PAPER_SOURCES_LABEL}",
    ),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索学术论文 — 支持多数据源并联查询。"""
    from souwen.core.exceptions import SouWenError
    from souwen.search import search_papers

    requested_sources = None
    if sources is None:
        source_list = list(_DEFAULT_PAPER_SOURCES)
    else:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]
        requested_sources = source_list
    try:
        coro = search_papers(q, sources=requested_sources, per_page=per_page)
        if timeout is not None:
            results = await asyncio.wait_for(coro, timeout=timeout)
        else:
            results = await coro
        succeeded = [r.source for r in results]
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
    """搜索专利 — 支持多数据源并联查询。"""
    from souwen.core.exceptions import SouWenError
    from souwen.search import search_patents

    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    try:
        coro = search_patents(q, sources=source_list, per_page=per_page)
        if timeout is not None:
            results = await asyncio.wait_for(coro, timeout=timeout)
        else:
            results = await coro
        succeeded = [r.source for r in results]
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
    """搜索网页 — 支持 21+ 搜索引擎。"""
    from souwen.core.exceptions import SouWenError
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
    """搜索图片 — DuckDuckGo Images。"""
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
    """搜索视频 — DuckDuckGo Videos。"""
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
