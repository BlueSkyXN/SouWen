"""并发多引擎聚合搜索

移植自 SoSearch/src/search.rs
并发查询 DuckDuckGo、Yahoo、Brave 三个引擎，
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

logger = logging.getLogger("souwen.web.search")


async def _search_engine(
    engine_cls: type,
    query: str,
    max_results: int,
    **kwargs,
) -> list[WebSearchResult]:
    """搜索单个引擎（异常安全）"""
    try:
        async with engine_cls(**kwargs) as client:
            resp = await client.search(query, max_results=max_results)
            return list(resp.results)
    except Exception as e:
        logger.warning("%s 搜索失败: %s", engine_cls.__name__, e)
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
        "duckduckgo": DuckDuckGoClient,
        "yahoo": YahooClient,
        "brave": BraveClient,
    }
    
    selected = engines or list(engine_map.keys())
    
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
        len(all_results), query, selected,
    )
    
    return WebSearchResponse(
        query=query,
        source=SourceType.WEB_DUCKDUCKGO,  # 聚合搜索标记为主引擎
        results=all_results,
        total_results=len(all_results),
    )
