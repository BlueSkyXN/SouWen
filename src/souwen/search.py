"""SouWen 统一搜索门面 — 一个函数搞定所有搜索"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from souwen.models import SearchResponse

# ── 论文客户端 ──────────────────────────────────────────────
from souwen.paper.openalex import OpenAlexClient
from souwen.paper.semantic_scholar import SemanticScholarClient
from souwen.paper.crossref import CrossrefClient
from souwen.paper.arxiv import ArxivClient
from souwen.paper.dblp import DblpClient
from souwen.paper.core import CoreClient
from souwen.paper.pubmed import PubMedClient

# ── 专利客户端 ──────────────────────────────────────────────
from souwen.patent.patentsview import PatentsViewClient
from souwen.patent.pqai import PqaiClient
from souwen.patent.epo_ops import EpoOpsClient
from souwen.patent.uspto_odp import UsptoOdpClient
from souwen.patent.the_lens import TheLensClient
from souwen.patent.cnipa import CnipaClient
from souwen.patent.patsnap import PatSnapClient
from souwen.patent.google_patents import GooglePatentsClient

# ── Web 搜索 ───────────────────────────────────────────────
from souwen.web.search import web_search  # re-export

logger = logging.getLogger("souwen.search")

# ── 默认免费数据源 ─────────────────────────────────────────
_DEFAULT_PAPER_SOURCES: list[str] = [
    "openalex",
    "semantic_scholar",
    "crossref",
    "arxiv",
    "dblp",
]
_DEFAULT_PATENT_SOURCES: list[str] = ["patentsview", "pqai"]


# ── 通用客户端执行器 ───────────────────────────────────────


async def _run_client(cls: type, method_name: str, **kwargs: Any) -> SearchResponse:
    """打开异步客户端并调用指定方法"""
    async with cls() as client:
        return await getattr(client, method_name)(**kwargs)


async def _search_source(name: str, coro: Any) -> SearchResponse | None:
    """执行单个数据源搜索（异常安全）"""
    try:
        return await coro
    except Exception as e:
        logger.warning("%s 搜索失败: %s", name, e)
        return None


# ── 数据源映射 ─────────────────────────────────────────────

_PAPER_SOURCES: dict[str, Any] = {
    "openalex": lambda q, n, **kw: _run_client(
        OpenAlexClient,
        "search",
        query=q,
        per_page=n,
        **kw,
    ),
    "semantic_scholar": lambda q, n, **kw: _run_client(
        SemanticScholarClient,
        "search",
        query=q,
        limit=n,
        **kw,
    ),
    "crossref": lambda q, n, **kw: _run_client(
        CrossrefClient,
        "search",
        query=q,
        rows=n,
        **kw,
    ),
    "arxiv": lambda q, n, **kw: _run_client(
        ArxivClient,
        "search",
        query=q,
        max_results=n,
        **kw,
    ),
    "dblp": lambda q, n, **kw: _run_client(
        DblpClient,
        "search",
        query=q,
        hits=n,
        **kw,
    ),
    "core": lambda q, n, **kw: _run_client(
        CoreClient,
        "search",
        query=q,
        limit=n,
        **kw,
    ),
    "pubmed": lambda q, n, **kw: _run_client(
        PubMedClient,
        "search",
        query=q,
        retmax=n,
        **kw,
    ),
}

_PATENT_SOURCES: dict[str, Any] = {
    "patentsview": lambda q, n, **kw: _run_client(
        PatentsViewClient,
        "search",
        query={"_contains": {"patent_title": q}},
        per_page=n,
        **kw,
    ),
    "pqai": lambda q, n, **kw: _run_client(
        PqaiClient,
        "search",
        query=q,
        n_results=n,
        **kw,
    ),
    "epo_ops": lambda q, n, **kw: _run_client(
        EpoOpsClient,
        "search",
        cql_query=q,
        range_end=n,
        **kw,
    ),
    "uspto_odp": lambda q, n, **kw: _run_client(
        UsptoOdpClient,
        "search_applications",
        query=q,
        per_page=n,
        **kw,
    ),
    "the_lens": lambda q, n, **kw: _run_client(
        TheLensClient,
        "search_patents",
        query=q,
        size=n,
        **kw,
    ),
    "cnipa": lambda q, n, **kw: _run_client(
        CnipaClient,
        "search",
        query=q,
        per_page=n,
        **kw,
    ),
    "patsnap": lambda q, n, **kw: _run_client(
        PatSnapClient,
        "search",
        query=q,
        limit=n,
        **kw,
    ),
    "google_patents": lambda q, n, **kw: _run_client(
        GooglePatentsClient,
        "search",
        query=q,
        num_results=n,
        **kw,
    ),
}


# ── 公开 API ───────────────────────────────────────────────


async def search_papers(
    query: str,
    sources: list[str] | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """并发多源论文搜索

    Args:
        query: 搜索关键词
        sources: 数据源列表，默认使用免费源 ["openalex", "semantic_scholar", "crossref", "arxiv", "dblp"]
        per_page: 每个源返回的结果数
        **kwargs: 额外参数传递给各客户端的 search 方法

    Returns:
        每个数据源一个 SearchResponse 的列表
    """
    selected = sources or _DEFAULT_PAPER_SOURCES
    tasks: list[tuple[str, Any]] = []
    for name in selected:
        factory = _PAPER_SOURCES.get(name)
        if factory is None:
            logger.warning("未知论文数据源: %s，跳过", name)
            continue
        tasks.append((name, factory(query, per_page, **kwargs)))

    results = await asyncio.gather(
        *[_search_source(n, coro) for n, coro in tasks],
        return_exceptions=True,
    )

    responses: list[SearchResponse] = []
    for r in results:
        if isinstance(r, SearchResponse):
            responses.append(r)
        elif isinstance(r, Exception):
            logger.warning("论文搜索异常: %s", r)

    logger.info(
        "论文搜索完成: %d/%d 源成功 (query=%s)",
        len(responses),
        len(tasks),
        query,
    )
    return responses


async def search_patents(
    query: str,
    sources: list[str] | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """并发多源专利搜索

    Args:
        query: 搜索关键词
        sources: 数据源列表，默认使用免费源 ["patentsview", "pqai"]
        per_page: 每个源返回的结果数
        **kwargs: 额外参数传递给各客户端的 search 方法

    Returns:
        每个数据源一个 SearchResponse 的列表
    """
    selected = sources or _DEFAULT_PATENT_SOURCES
    tasks: list[tuple[str, Any]] = []
    for name in selected:
        factory = _PATENT_SOURCES.get(name)
        if factory is None:
            logger.warning("未知专利数据源: %s，跳过", name)
            continue
        tasks.append((name, factory(query, per_page, **kwargs)))

    results = await asyncio.gather(
        *[_search_source(n, coro) for n, coro in tasks],
        return_exceptions=True,
    )

    responses: list[SearchResponse] = []
    for r in results:
        if isinstance(r, SearchResponse):
            responses.append(r)
        elif isinstance(r, Exception):
            logger.warning("专利搜索异常: %s", r)

    logger.info(
        "专利搜索完成: %d/%d 源成功 (query=%s)",
        len(responses),
        len(tasks),
        query,
    )
    return responses


async def search(
    query: str,
    domain: str = "paper",
    **kwargs: Any,
) -> list[SearchResponse]:
    """统一搜索入口 — 根据 domain 分发

    Args:
        query: 搜索关键词
        domain: 搜索领域 "paper" | "patent" | "web"
        **kwargs: 传递给对应搜索函数的参数
    """
    if domain == "paper":
        return await search_papers(query, **kwargs)
    elif domain == "patent":
        return await search_patents(query, **kwargs)
    elif domain == "web":
        resp = await web_search(query, **kwargs)
        return [resp]
    else:
        raise ValueError(f"未知搜索领域: {domain!r}，支持 'paper' | 'patent' | 'web'")
