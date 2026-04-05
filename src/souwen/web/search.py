"""并发多引擎聚合搜索

并发查询 DuckDuckGo、Yahoo、Brave 等多个引擎，
聚合结果并去重。

技术要点：
- asyncio.gather 并发（等价 Rust 的 FuturesUnordered + tokio::spawn）
- 部分引擎失败不影响整体结果
- URL 去重避免重复结果
"""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from souwen.models import WebSearchResult, WebSearchResponse, SourceType
from souwen.web.duckduckgo import DuckDuckGoClient
from souwen.web.yahoo import YahooClient
from souwen.web.brave import BraveClient
from souwen.web.google import GoogleClient
from souwen.web.bing import BingClient
from souwen.web.searxng import SearXNGClient
from souwen.web.tavily import TavilyClient
from souwen.web.exa import ExaClient
from souwen.web.serper import SerperClient
from souwen.web.brave_api import BraveApiClient
from souwen.web.serpapi import SerpApiClient
from souwen.web.firecrawl import FirecrawlClient
from souwen.web.perplexity import PerplexityClient
from souwen.web.linkup import LinkupClient
from souwen.web.scrapingdog import ScrapingDogClient
from souwen.web.startpage import StartpageClient
from souwen.web.baidu import BaiduClient
from souwen.web.mojeek import MojeekClient
from souwen.web.yandex import YandexClient
from souwen.web.whoogle import WhoogleClient
from souwen.web.websurfx import WebsurfxClient

logger = logging.getLogger("souwen.web.search")

# 全局并发度限制（Web 引擎共享）
_WEB_SEMAPHORE = asyncio.Semaphore(10)


async def _search_engine(
    engine_cls: type,
    query: str,
    max_results: int,
    **kwargs,
) -> list[WebSearchResult]:
    """搜索单个引擎（异常安全 + 并发度限制）"""
    async with _WEB_SEMAPHORE:
        try:
            async with engine_cls(**kwargs) as client:
                resp = await client.search(query, max_results=max_results)
                return list(resp.results)
        except Exception as e:
            logger.warning("%s 搜索失败 [%s]: %s", engine_cls.__name__, type(e).__name__, e)
            return []


def _deduplicate(results: Sequence[WebSearchResult]) -> list[WebSearchResult]:
    """URL 去重，保留首次出现的结果"""
    seen_urls: set[str] = set()
    deduped: list[WebSearchResult] = []
    for r in results:
        normalized = r.url.rstrip("/").lower()
        if normalized not in seen_urls:
            seen_urls.add(normalized)
            deduped.append(r)
    return deduped


async def web_search(
    query: str,
    engines: list[str] | None = None,
    max_results_per_engine: int = 10,
    deduplicate: bool = True,
    **kwargs,
) -> WebSearchResponse:
    """并发多引擎聚合搜索

    同时查询 DuckDuckGo、Yahoo、Brave（或指定子集），
    聚合结果并可选去重。

    Args:
        query: 搜索关键词
        engines: 引擎列表，默认全部 ["duckduckgo", "yahoo", "brave"]
        max_results_per_engine: 每个引擎最大返回数
        deduplicate: 是否按 URL 去重
        **kwargs: 传递给各引擎构造函数的参数（如 use_curl_cffi）

    Returns:
        WebSearchResponse 聚合结果

    Example:
        >>> resp = await web_search("Python asyncio tutorial")
        >>> for r in resp.results:
        ...     print(f"[{r.engine}] {r.title} → {r.url}")
    """
    engine_map: dict[str, type] = {
        # 爬虫引擎（无需 API Key）
        "duckduckgo": DuckDuckGoClient,
        "yahoo": YahooClient,
        "brave": BraveClient,
        "google": GoogleClient,
        "bing": BingClient,
        "startpage": StartpageClient,
        "baidu": BaiduClient,
        "mojeek": MojeekClient,
        "yandex": YandexClient,
        # API 引擎（需要对应 Key）
        "searxng": SearXNGClient,
        "tavily": TavilyClient,
        "exa": ExaClient,
        "serper": SerperClient,
        "brave_api": BraveApiClient,
        "serpapi": SerpApiClient,
        "firecrawl": FirecrawlClient,
        "perplexity": PerplexityClient,
        "linkup": LinkupClient,
        "scrapingdog": ScrapingDogClient,
        # 自部署元搜索（需自建实例）
        "whoogle": WhoogleClient,
        "websurfx": WebsurfxClient,
    }

    # 默认使用 3 个最稳定的免费引擎
    # Google/Bing 爬虫风险较高，需显式指定
    selected = engines or ["duckduckgo", "yahoo", "brave"]

    tasks = []
    for name in selected:
        cls = engine_map.get(name)
        if cls is None:
            logger.warning("未知引擎: %s，跳过", name)
            continue
        tasks.append(_search_engine(cls, query, max_results_per_engine, **kwargs))

    # 并发执行所有引擎（等价 Rust 的 FuturesUnordered + tokio::spawn）
    engine_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: list[WebSearchResult] = []
    for result in engine_results:
        if isinstance(result, list):
            all_results.extend(result)
        elif isinstance(result, Exception):
            logger.warning("引擎返回异常: %s", result)

    if deduplicate:
        all_results = _deduplicate(all_results)

    logger.info(
        "聚合搜索完成: %d 条结果 (query=%s, engines=%s)",
        len(all_results),
        query,
        selected,
    )

    return WebSearchResponse(
        query=query,
        source=SourceType.WEB_DUCKDUCKGO,  # 聚合搜索标记为主引擎
        results=all_results,
        total_results=len(all_results),
    )
