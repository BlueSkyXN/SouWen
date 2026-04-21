"""SouWen 统一搜索门面 — 一个函数搞定所有搜索

文件用途：
    提供统一的异步搜索接口，支持论文、专利、网页搜索。通过并发调用多个数据源客户端，
    快速聚合结果并返回 SearchResponse 列表。

函数清单（[已修正] 与实际签名对齐）：
    search(query, domain="paper", **kwargs) → list[SearchResponse]
        - 功能：统一搜索入口，按 domain 分发到 paper/patent/web 子函数
        - 参数：query 搜索词；domain 取 "paper" | "patent" | "web"；
                **kwargs 透传给对应子函数
        - 返回：每个数据源一个 SearchResponse 的列表（web 域返回单元素列表）
        - 异常：未知 domain 抛 ValueError

    search_papers(query, sources=None, per_page=10, **kwargs) → list[SearchResponse]
        - 功能：并发多源论文搜索
        - 参数：sources 源名称列表（默认 _DEFAULT_PAPER_SOURCES：openalex/crossref/arxiv/dblp/pubmed）
                per_page 每源返回数量；**kwargs 透传给客户端 search 方法
        - 返回：成功源的 SearchResponse 列表（失败/被禁用的源会被跳过）

    search_patents(query, sources=None, per_page=10, **kwargs) → list[SearchResponse]
        - 功能：并发多源专利搜索
        - 参数：sources 默认 _DEFAULT_PATENT_SOURCES（["google_patents"]）
                per_page 每源返回数量

    web_search（从 souwen.web.search 重导出）
        - 功能：网页搜索入口（异步），用于 search(domain="web") 路径

    _run_client(cls, method_name, **kwargs) → SearchResponse
        - 功能：辅助函数，进入异步上下文并调用指定方法

    _search_source(name, coro) → SearchResponse | None
        - 功能：执行单个数据源搜索（异常安全）
        - 特点：ConfigError → info 跳过；RateLimitError/其他 → warning 但不抛出

    _search_source_limited(name, coro) → SearchResponse | None
        - 功能：在 _search_source 外层加上 Semaphore 并发限制 + asyncio.wait_for 超时

    _get_source_timeout_seconds() → float
        - 功能：返回单个源的搜索超时（受 _SEARCH_SOURCE_TIMEOUT_CAP_SECONDS=15s 上限约束）

    _get_max_concurrency() → int
        - 功能：读取并发上限（默认 10，可由环境变量 SOUWEN_MAX_CONCURRENCY 覆盖）

    _get_semaphore() → asyncio.Semaphore
        - 功能：返回与当前 running event loop 绑定的 Semaphore（per-loop 懒加载）

默认数据源：
    论文：OpenAlex, CrossRef, arXiv, DBLP, PubMed（免费源）
    专利：Google Patents Scraper（免费源）
    网页：由 souwen.web.search 自动选择

并发策略：
    - asyncio.gather 并发调用多个源，最大化效率
    - 全局并发度上限通过 Semaphore 限制（默认 10）
    - 单源超时上限 _SEARCH_SOURCE_TIMEOUT_CAP_SECONDS = 15s
    - 单源异常被捕获，不阻止其他源继续执行（异常安全）

模块依赖：
    - souwen.config: 获取全局配置
    - souwen.models: SearchResponse
    - souwen.paper.*: 各论文客户端
    - souwen.patent.*: 各专利客户端
    - souwen.scraper.google_patents_scraper: Google Patents 爬虫
    - souwen.web.search: Web 搜索实现
"""

from __future__ import annotations

import asyncio
import logging
import os
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
from souwen.paper.zotero import ZoteroClient

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
    """打开异步客户端并调用指定方法

    辅助函数，简化客户端的创建和方法调用。

    Args:
        cls: 客户端类（如 OpenAlexClient）
        method_name: 要调用的方法名（通常是 'search'）
        **kwargs: 传给方法的参数

    Returns:
        SearchResponse 对象
    """
    async with cls() as client:
        return await getattr(client, method_name)(**kwargs)


async def _search_source(name: str, coro: Any) -> SearchResponse | None:
    """执行单个数据源搜索（异常安全）

    捕获和处理异常，区分类型：
    - AuthError: 认证失败，记录警告日志
    - SourceUnavailableError: 源不可用，记录信息日志
    - 其他异常：忽略，返回 None（避免阻止其他源）

    Args:
        name: 数据源名称（用于日志）
        coro: 异步协程（通常来自 _run_client）

    Returns:
        SearchResponse 对象或 None（失败时）
    """
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
_DEFAULT_MAX_CONCURRENCY = 10


def _get_max_concurrency() -> int:
    """读取并发上限（允许通过 SOUWEN_MAX_CONCURRENCY 覆盖）"""
    raw = os.environ.get("SOUWEN_MAX_CONCURRENCY")
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return _DEFAULT_MAX_CONCURRENCY


def _get_semaphore() -> asyncio.Semaphore:
    """返回与当前 running event loop 绑定的 Semaphore（per-loop 懒加载）"""
    loop = asyncio.get_running_loop()
    sem = getattr(loop, "_souwen_sem", None)
    if sem is None:
        sem = asyncio.Semaphore(_get_max_concurrency())
        loop._souwen_sem = sem  # type: ignore[attr-defined]
    return sem


async def _search_source_limited(name: str, coro: Any) -> SearchResponse | None:
    """带并发度限制的搜索执行"""
    async with _get_semaphore():
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
    "zotero": lambda q, n, **kw: _run_client(
        ZoteroClient,
        "search",
        query=q,
        limit=n,
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
    cfg = get_config()
    for name in selected:
        if not cfg.is_source_enabled(name):
            logger.info("数据源 %s 已禁用，跳过", name)
            continue
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
    cfg = get_config()
    for name in selected:
        if not cfg.is_source_enabled(name):
            logger.info("数据源 %s 已禁用，跳过", name)
            continue
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
