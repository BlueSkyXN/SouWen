"""SouWen 统一搜索门面 — 一个函数搞定所有搜索"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from souwen.config import get_config
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
from souwen.scraper.google_patents_scraper import GooglePatentsScraper

# ── Web 搜索 ───────────────────────────────────────────────
from souwen.web.search import web_search  # re-export

logger = logging.getLogger("souwen.search")
_SEARCH_SOURCE_TIMEOUT_CAP_SECONDS = 15.0

# ── 默认免费数据源 ─────────────────────────────────────────
_DEFAULT_PAPER_SOURCES: list[str] = [
    "openalex",
    "crossref",
    "arxiv",
    "dblp",
    "pubmed",
]
_DEFAULT_PATENT_SOURCES: list[str] = ["google_patents"]


# ── 通用客户端执行器 ───────────────────────────────────────


async def _run_client(cls: type, method_name: str, **kwargs: Any) -> SearchResponse:
    """打开异步客户端并调用指定方法"""
    async with cls() as client:
        return await getattr(client, method_name)(**kwargs)


async def _search_source(name: str, coro: Any) -> SearchResponse | None:
    """执行单个数据源搜索（异常安全，区分异常类型）"""
    try:
        return await coro
    except Exception as e:
        from souwen.exceptions import ConfigError, RateLimitError

        if isinstance(e, ConfigError):
            logger.info("%s 跳过: 缺少配置 (%s)", name, e)
        elif isinstance(e, RateLimitError):
            logger.warning("%s 被限流: %s", name, e)
        else:
            logger.warning("%s 搜索失败 [%s]: %s", name, type(e).__name__, e)
        return None


def _get_source_timeout_seconds() -> float:
    """单个数据源搜索的聚合超时，避免慢源拖住整次请求。"""
    timeout = float(get_config().timeout)
    return max(1.0, min(timeout, _SEARCH_SOURCE_TIMEOUT_CAP_SECONDS))


# 全局并发度限制，防止同时打满 Socket 连接
_CONCURRENCY_SEMAPHORE = asyncio.Semaphore(10)


async def _search_source_limited(name: str, coro: Any) -> SearchResponse | None:
    """带并发度限制的搜索执行"""
    async with _CONCURRENCY_SEMAPHORE:
        timeout = _get_source_timeout_seconds()
        try:
            return await asyncio.wait_for(_search_source(name, coro), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s 搜索超时，已跳过 (%.1fs)", name, timeout)
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
        GooglePatentsScraper,
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
        sources: 数据源列表，默认使用较稳定免费源 ["openalex", "crossref", "arxiv", "dblp", "pubmed"]
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
        *[_search_source_limited(n, coro) for n, coro in tasks],
    )

    responses = [r for r in results if isinstance(r, SearchResponse)]
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
        sources: 数据源列表，默认使用实验性免费源 ["google_patents"]
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
        *[_search_source_limited(n, coro) for n, coro in tasks],
    )

    responses = [r for r in results if isinstance(r, SearchResponse)]

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
