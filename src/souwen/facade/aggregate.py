"""facade/aggregate.py — 多 domain 并发聚合搜索（D1）

`search-all` 是 v1 的显式聚合入口，接受 `domains` 参数，并发调用多个
`search(domain=X)` 并按 domain 分组返回结果。与 v1 的"严格分域"设计相对：
默认的 `search(domain='paper')` 不会混合其他 domain 的结果；想跨域只能显式
调 search_all。

公开 API：
  - search_all(query, domains=None, per_domain_limit=5, timeout=None) →
      dict[str, list[SearchResponse]]
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from souwen.models import SearchResponse

logger = logging.getLogger("souwen.facade.aggregate")

DEFAULT_DOMAINS: tuple[str, ...] = ("paper", "web", "knowledge", "developer")


async def search_all(
    query: str,
    domains: list[str] | None = None,
    per_domain_limit: int = 5,
    timeout: float | None = None,
    **kwargs: Any,
) -> dict[str, list[SearchResponse]]:
    """跨多个 domain 并行搜索，按 domain 分组返回。

    Args:
        query: 搜索关键词
        domains: 要搜索的 domain 列表；None 用 DEFAULT_DOMAINS
        per_domain_limit: 每个 domain 返回多少结果（透传给各 domain 的 limit）
        timeout: 每个 domain 子任务的整体超时（秒）；None 不设超时
        **kwargs: 透传给 search()

    Returns:
        `{domain: [SearchResponse, ...], ...}` 字典。失败/超时的 domain 返回空列表。
    """
    from souwen.facade.search import search

    selected = list(domains) if domains else list(DEFAULT_DOMAINS)
    results: dict[str, list[SearchResponse]] = {}

    async def _run_one(dom: str) -> tuple[str, list[SearchResponse]]:
        try:
            if timeout is not None:
                resp = await asyncio.wait_for(
                    search(query, dom, limit=per_domain_limit, **kwargs),
                    timeout=timeout,
                )
            else:
                resp = await search(query, dom, limit=per_domain_limit, **kwargs)
            return dom, resp
        except asyncio.TimeoutError:
            logger.warning("search-all: domain=%s 超时（%.1fs）", dom, timeout or 0)
            return dom, []
        except Exception as e:
            logger.warning("search-all: domain=%s 失败 [%s]: %s", dom, type(e).__name__, e)
            return dom, []

    pairs = await asyncio.gather(*[_run_one(d) for d in selected])
    for dom, resp in pairs:
        results[dom] = resp
    return results
