"""搜索端点 — 论文 / 专利 / 网页 / 新闻 / 图片 / 视频"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from souwen.editions import EditionError
from souwen.registry import defaults_for
from souwen.server.auth import check_search_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.routes._common import logger
from souwen.server.schemas import (
    EnrichedWebSearchRequest,
    EnrichedWebSearchResponse,
    SearchImagesResponse,
    SearchBookResponse,
    SearchResearchOutputResponse,
    SearchPaperResponse,
    SearchPatentResponse,
    SearchVideosResponse,
    SearchWebResponse,
)

router = APIRouter()


def _default_paper_sources() -> list[str]:
    """返回当前 registry 的论文默认源。"""
    return defaults_for("paper", "search")


def _default_book_sources() -> list[str]:
    """返回当前 registry 的图书默认源。"""
    return defaults_for("book", "search")


def _default_research_output_sources() -> list[str]:
    """返回当前 registry 的科研产出默认源。"""
    return defaults_for("research_output", "search")


def _default_patent_sources() -> list[str]:
    """返回当前 registry 的专利默认源。"""
    return defaults_for("patent", "search")


def _default_web_engines() -> list[str]:
    """返回当前 registry 的网页搜索默认引擎。"""
    return defaults_for("web", "search")


def _default_web_capability_sources(capability: str) -> list[str]:
    """返回当前 registry 的 Web 扩展搜索默认源。"""
    return defaults_for("web", capability)


def _normalize_query_arg(q: str) -> str:
    """Normalize GET search q parameter before invoking upstream clients."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="q 不能是空字符串")
    return query


def _normalize_csv_arg(value: str | None) -> tuple[list[str], list[str] | None]:
    """Normalize optional comma-separated source/engine query arguments."""
    if value is None:
        return [], None
    names = [item.strip() for item in value.split(",") if item.strip()]
    return names, names


async def _run_registry_web_capability_search(
    *,
    query: str,
    capability: str,
    source_list: list[str],
    requested_sources: list[str] | None,
    max_results: int,
    region: str,
    safesearch: str,
    timeout: float | None,
    timeout_label: str,
    unavailable_detail: str,
    response_sources_field: str | None = None,
    **extra_kwargs: object,
) -> dict:
    """Dispatch a web capability through the registry-backed search facade."""
    from souwen.search import search

    try:
        coro = search(
            query,
            domain="web",
            capability=capability,
            sources=requested_sources,
            limit=max_results,
            region=region,
            safesearch=safesearch,
            **extra_kwargs,
        )
        if timeout is not None:
            responses = await asyncio.wait_for(coro, timeout=timeout)
        else:
            responses = await coro

        results_dump: list[dict] = []
        succeeded: list[str] = []
        for resp in responses:
            source = getattr(resp, "source", None)
            if isinstance(source, str) and source:
                succeeded.append(source)
            for item in getattr(resp, "results", []) or []:
                if hasattr(item, "model_dump"):
                    results_dump.append(item.model_dump(mode="json"))
                else:
                    results_dump.append(item)

        requested = source_list
        failed = [name for name in requested if name not in succeeded]
        if requested and not succeeded and not results_dump:
            raise HTTPException(status_code=502, detail=unavailable_detail)
        payload = {
            "query": query,
            "results": results_dump,
            "total": len(results_dump),
            "meta": {
                "requested": requested,
                "succeeded": succeeded,
                "failed": failed,
            },
        }
        if response_sources_field is not None:
            payload[response_sources_field] = requested
        return payload
    except asyncio.TimeoutError:
        logger.warning("%s搜索超时: q=%s timeout=%ss", timeout_label, query, timeout)
        raise HTTPException(status_code=504, detail=f"{timeout_label}搜索超时（{timeout}s）")
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except HTTPException:
        raise
    except Exception:
        logger.warning("%s搜索内部错误: q=%s", timeout_label, query, exc_info=True)
        raise HTTPException(status_code=502, detail=unavailable_detail)


@router.get(
    "/search/book",
    response_model=SearchBookResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_book(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str | None = Query(
        None,
        description="数据源，逗号分隔；默认来自当前 registry 的 book:search",
    ),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索 work 级图书书目。"""
    from souwen.core.exceptions import LocalCatalogUnavailableError, SouWenError
    from souwen.search import search_books

    query = _normalize_query_arg(q)
    requested_sources = None
    if sources is None:
        source_list = _default_book_sources()
    else:
        source_list = [source.strip() for source in sources.split(",") if source.strip()]
        requested_sources = source_list
    try:
        coro = search_books(query, sources=requested_sources, per_page=per_page)
        results = (
            await asyncio.wait_for(coro, timeout=timeout) if timeout is not None else await coro
        )
        succeeded = [result.source for result in results]
        return {
            "query": query,
            "sources": source_list,
            "results": [result.model_dump(mode="json") for result in results],
            "total": sum(len(result.results) for result in results),
            "meta": {
                "requested": source_list,
                "succeeded": succeeded,
                "failed": [source for source in source_list if source not in succeeded],
            },
        }
    except asyncio.TimeoutError:
        logger.warning("图书搜索超时: q=%s timeout=%ss", query, timeout)
        raise HTTPException(status_code=504, detail=f"搜索超时（{timeout}s）")
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except LocalCatalogUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="local catalog unavailable; run `souwen catalog import gutenberg <rdf-input>`",
        )
    except SouWenError:
        logger.exception("图书搜索上游失败: q=%s sources=%s", query, source_list)
        raise HTTPException(status_code=502, detail="所有上游数据源均不可用")


@router.get(
    "/search/research-output",
    response_model=SearchResearchOutputResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_research_output(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str | None = Query(
        None,
        description="数据源，逗号分隔；默认来自当前 registry 的 research_output:search",
    ),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索数据集、软件、文本、活动等非论文科研产出。"""
    from souwen.core.exceptions import SouWenError
    from souwen.search import search_research_outputs

    query = _normalize_query_arg(q)
    requested_sources = None
    if sources is None:
        source_list = _default_research_output_sources()
    else:
        source_list = [source.strip() for source in sources.split(",") if source.strip()]
        requested_sources = source_list
    try:
        coro = search_research_outputs(query, sources=requested_sources, per_page=per_page)
        results = (
            await asyncio.wait_for(coro, timeout=timeout) if timeout is not None else await coro
        )
        succeeded = [result.source for result in results]
        return {
            "query": query,
            "sources": source_list,
            "results": results,
            "total": sum(len(result.results) for result in results),
            "meta": {
                "requested": source_list,
                "succeeded": succeeded,
                "failed": [source for source in source_list if source not in succeeded],
            },
        }
    except asyncio.TimeoutError:
        logger.warning("科研产出搜索超时: q=%s timeout=%ss", query, timeout)
        raise HTTPException(status_code=504, detail=f"搜索超时（{timeout}s）")
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SouWenError:
        logger.exception("科研产出搜索上游失败: q=%s sources=%s", query, source_list)
        raise HTTPException(status_code=502, detail="所有上游数据源均不可用")


@router.get(
    "/search/paper",
    response_model=SearchPaperResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_paper(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str | None = Query(
        None,
        description="数据源，逗号分隔；默认来自当前 registry 的 paper:search",
    ),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索学术论文 — 支持多数据源并联查询。"""
    from souwen.core.exceptions import SouWenError
    from souwen.search import search_papers

    query = _normalize_query_arg(q)
    requested_sources = None
    if sources is None:
        source_list = _default_paper_sources()
    else:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]
        requested_sources = source_list
    try:
        coro = search_papers(query, sources=requested_sources, per_page=per_page)
        if timeout is not None:
            results = await asyncio.wait_for(coro, timeout=timeout)
        else:
            results = await coro
        succeeded = [r.source for r in results]
        return {
            "query": query,
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
        logger.warning("论文搜索超时: q=%s timeout=%ss", query, timeout)
        raise HTTPException(status_code=504, detail=f"搜索超时（{timeout}s）")
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SouWenError:
        logger.exception("论文搜索上游失败: q=%s sources=%s", query, source_list)
        raise HTTPException(status_code=502, detail="所有上游数据源均不可用")
    except Exception:
        logger.warning("论文搜索内部错误: q=%s", query, exc_info=True)
        raise


@router.get(
    "/search/patent",
    response_model=SearchPatentResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_patent(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str | None = Query(
        None,
        description="数据源，逗号分隔；默认来自当前 registry 的 patent:search",
    ),
    per_page: int = Query(10, ge=1, le=100, description="每页结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索专利 — 支持多数据源并联查询。"""
    from souwen.core.exceptions import SouWenError
    from souwen.search import search_patents

    query = _normalize_query_arg(q)
    requested_sources = None
    if sources is None:
        source_list = _default_patent_sources()
    else:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]
        requested_sources = source_list
    try:
        coro = search_patents(query, sources=requested_sources, per_page=per_page)
        if timeout is not None:
            results = await asyncio.wait_for(coro, timeout=timeout)
        else:
            results = await coro
        succeeded = [r.source for r in results]
        return {
            "query": query,
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
        logger.warning("专利搜索超时: q=%s timeout=%ss", query, timeout)
        raise HTTPException(status_code=504, detail=f"搜索超时（{timeout}s）")
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SouWenError:
        logger.exception("专利搜索上游失败: q=%s sources=%s", query, source_list)
        raise HTTPException(status_code=502, detail="所有上游数据源均不可用")
    except Exception:
        logger.warning("专利搜索内部错误: q=%s", query, exc_info=True)
        raise


@router.get(
    "/search/web",
    response_model=SearchWebResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_web(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    engines: str | None = Query(
        None,
        description="搜索引擎，逗号分隔；默认来自当前 registry 的 web:search",
    ),
    per_page: int = Query(
        10, ge=1, le=50, alias="per_page", description="每引擎最大结果数（别名: max_results）"
    ),
    max_results: int | None = Query(None, ge=1, le=50, description="兼容旧版：每引擎最大结果数"),
    timeout: float | None = Query(None, ge=1, le=300, description="端点硬超时（秒），超时返回 504"),
):
    """搜索网页 — 支持 21+ 搜索引擎。"""
    from souwen.core.exceptions import SouWenError
    from souwen.web.search import web_search

    query = _normalize_query_arg(q)
    requested_engines = None
    if engines is None:
        engine_list = _default_web_engines()
    else:
        engine_list = [e.strip() for e in engines.split(",") if e.strip()]
        requested_engines = engine_list
    effective = max_results if max_results is not None else per_page
    try:
        coro = web_search(query, engines=requested_engines, max_results_per_engine=effective)
        if timeout is not None:
            resp = await asyncio.wait_for(coro, timeout=timeout)
        else:
            resp = await coro
        results_dump = [r.model_dump(mode="json") for r in resp.results]
        succeeded = sorted({r.engine for r in resp.results})
        failed = [e for e in engine_list if e not in succeeded]
        return {
            "query": query,
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
        logger.warning("网页搜索超时: q=%s timeout=%ss", query, timeout)
        raise HTTPException(status_code=504, detail=f"搜索超时（{timeout}s）")
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SouWenError:
        logger.exception("网页搜索上游失败: q=%s engines=%s", query, engine_list)
        raise HTTPException(status_code=502, detail="所有上游搜索引擎均不可用")
    except Exception:
        logger.warning("网页搜索内部错误: q=%s", query, exc_info=True)
        raise


@router.post(
    "/search/web/enriched",
    response_model=EnrichedWebSearchResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_web_enriched(body: EnrichedWebSearchRequest):
    """Search explicit model-bound sources, then optionally enrich with safe fetches."""
    from souwen.llm.enriched_synthesis import EnrichedSynthesisProfileError
    from souwen.web.enriched_search import (
        EnrichedSearchDeadlineExceeded,
        EnrichedSearchSourceDisabledError,
        EnrichedSearchSourceValidationError,
        EnrichedSearchUnavailableError,
        EnrichedSearchUnknownSourceError,
        enriched_web_search,
    )

    try:
        execution = await asyncio.wait_for(
            enriched_web_search(
                body.query,
                sources=body.sources,
                source_strategy=body.source_strategy,
                max_results_per_source=body.max_results_per_source,
                max_source_attempts=body.budget.max_source_attempts,
                deadline_seconds=body.budget.max_total_seconds,
                deduplicate=body.deduplicate,
                fetch=body.fetch.enabled,
                fetch_providers=body.fetch.providers,
                fetch_strategy=body.fetch.strategy,
                max_pages=body.fetch.max_pages,
                fetch_timeout=body.budget.max_total_seconds,
                include_content=body.fetch.include_content,
                max_content_chars=body.fetch.max_content_chars,
                excerpt_chars=body.fetch.max_excerpt_chars,
                synthesis_profile=body.synthesis.profile if body.synthesis is not None else None,
            ),
            timeout=body.budget.max_total_seconds,
        )
    except EnrichedSearchUnknownSourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EnrichedSearchSourceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EnrichedSearchSourceDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EnrichedSynthesisProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (EnrichedSearchDeadlineExceeded, asyncio.TimeoutError) as exc:
        logger.warning("enriched 网页搜索超时: sources=%s", body.sources)
        raise HTTPException(status_code=504, detail="enriched 网页搜索超时") from exc
    except EnrichedSearchUnavailableError as exc:
        raise HTTPException(status_code=502, detail="所有 enriched search source 均不可用") from exc
    except Exception:
        logger.warning("enriched 网页搜索内部错误: sources=%s", body.sources, exc_info=True)
        raise HTTPException(status_code=502, detail="enriched 网页搜索不可用") from None

    return {
        "query": execution.query,
        "results": [result.model_dump(mode="json") for result in execution.results],
        "answer": execution.answer.model_dump(mode="json")
        if execution.answer is not None
        else None,
        "meta": {
            "requested_sources": body.sources,
            "source_strategy": body.source_strategy,
            "source_outcomes": execution.source_outcomes,
            "partial": execution.partial,
            "discarded_candidates": execution.discarded_candidates,
            "source_attempts": [
                {
                    "source_id": attempt.source_id,
                    "attempt_index": attempt.attempt_index,
                    "outcome": attempt.outcome,
                    "visible_search_calls": attempt.visible_search_calls,
                    "provider_metered_search_calls": attempt.provider_metered_search_calls,
                }
                for attempt in execution.source_attempts
            ],
            "visible_search_calls": execution.visible_search_calls,
            "provider_metered_search_calls": execution.provider_metered_search_calls,
            "fetched_pages": execution.fetched_pages,
            "synthesis_status": execution.synthesis_status,
            "summarized_pages": sum(
                1 for result in execution.results if result.summary is not None
            ),
        },
        "usage": {
            "search_input_tokens": None,
            "search_output_tokens": None,
            "summary_input_tokens": (
                execution.summary_usage.prompt_tokens
                if execution.summary_usage is not None
                else None
            ),
            "summary_output_tokens": (
                execution.summary_usage.completion_tokens
                if execution.summary_usage is not None
                else None
            ),
            "search_tool_cost": None,
            "currency": None,
        },
    }


@router.get(
    "/search/news",
    response_model=SearchWebResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_news(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str | None = Query(
        None,
        description="新闻搜索源，逗号分隔；默认来自当前 registry 的 web:search_news",
    ),
    max_results: int = Query(20, ge=1, le=100, description="最大结果数"),
    region: str = Query("wt-wt", description="区域 (wt-wt=全球, cn-zh=中国)"),
    safesearch: str = Query("moderate", description="安全搜索 (on/moderate/off)"),
    time_range: str | None = Query(None, description="时间范围 (d/w/m)，为空表示不限"),
    timeout: float | None = Query(None, ge=1, le=120, description="端点硬超时（秒），超时返回 504"),
):
    """搜索新闻 — 从 registry 的 web:search_news capability 派发。"""
    query = _normalize_query_arg(q)
    source_list, requested_sources = _normalize_csv_arg(sources)
    if requested_sources is None:
        source_list = _default_web_capability_sources("search_news")
    return await _run_registry_web_capability_search(
        query=query,
        capability="search_news",
        source_list=source_list,
        requested_sources=requested_sources,
        max_results=max_results,
        region=region,
        safesearch=safesearch,
        timeout=timeout,
        timeout_label="新闻",
        unavailable_detail="新闻搜索引擎不可用",
        response_sources_field="engines",
        time_range=time_range,
    )


@router.get(
    "/search/images",
    response_model=SearchImagesResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_images(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str | None = Query(
        None,
        description="图片搜索源，逗号分隔；默认来自当前 registry 的 web:search_images",
    ),
    max_results: int = Query(20, ge=1, le=100, description="最大结果数"),
    region: str = Query("wt-wt", description="区域 (wt-wt=全球, cn-zh=中国)"),
    safesearch: str = Query("moderate", description="安全搜索 (on/moderate/off)"),
    timeout: float | None = Query(None, ge=1, le=120, description="端点硬超时（秒），超时返回 504"),
):
    """搜索图片 — 从 registry 的 web:search_images capability 派发。"""
    query = _normalize_query_arg(q)
    source_list, requested_sources = _normalize_csv_arg(sources)
    if requested_sources is None:
        source_list = _default_web_capability_sources("search_images")
    return await _run_registry_web_capability_search(
        query=query,
        capability="search_images",
        source_list=source_list,
        requested_sources=requested_sources,
        max_results=max_results,
        region=region,
        safesearch=safesearch,
        timeout=timeout,
        timeout_label="图片",
        unavailable_detail="图片搜索引擎不可用",
    )


@router.get(
    "/search/videos",
    response_model=SearchVideosResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_search_videos(
    q: str = Query(..., description="搜索关键词", min_length=1, max_length=500),
    sources: str | None = Query(
        None,
        description="视频搜索源，逗号分隔；默认来自当前 registry 的 web:search_videos",
    ),
    max_results: int = Query(20, ge=1, le=100, description="最大结果数"),
    region: str = Query("wt-wt", description="区域"),
    safesearch: str = Query("moderate", description="安全搜索 (on/moderate/off)"),
    timeout: float | None = Query(None, ge=1, le=120, description="端点硬超时（秒），超时返回 504"),
):
    """搜索视频 — 从 registry 的 web:search_videos capability 派发。"""
    query = _normalize_query_arg(q)
    source_list, requested_sources = _normalize_csv_arg(sources)
    if requested_sources is None:
        source_list = _default_web_capability_sources("search_videos")
    return await _run_registry_web_capability_search(
        query=query,
        capability="search_videos",
        source_list=source_list,
        requested_sources=requested_sources,
        max_results=max_results,
        region=region,
        safesearch=safesearch,
        timeout=timeout,
        timeout_label="视频",
        unavailable_detail="视频搜索引擎不可用",
    )
