"""facade/search.py — 按 domain 统一搜索入口

本模块是搜索门面，派发给具体 adapter。`souwen.search` 是本模块的**入口别名**：
`souwen.search.search_papers` 与 `souwen.facade.search.search_papers` 是同一个东西。

公开 API：
  - search(query, domain="paper", capability="search", sources=None, limit=10, **kw)
      → list[SearchResponse]
      统一搜索入口，按 (domain, capability) 派发。

  - search_domain(query, domain, capability="search", ...)
      search() 的语义版本别名，显式传 domain。

  - search_by_capability(query, capability, sources=None, ...)
      忽略 domain，对所有支持某 capability 的源派发（谨慎使用，一般走 search_all）。

  - search_papers / search_patents —— 便捷入口，内部调 search(domain=...)。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from souwen.config import get_config
from souwen.core.concurrency import get_semaphore
from souwen.models import SearchResponse
from souwen.registry import defaults_for, get as _registry_get
from souwen.registry.adapter import SourceAdapter

logger = logging.getLogger("souwen.facade.search")

_SEARCH_SOURCE_TIMEOUT_CAP_SECONDS = 15.0


async def _run_via_adapter(
    adapter: SourceAdapter,
    capability: str,
    /,
    **unified_kwargs: Any,
) -> SearchResponse:
    """按 adapter 声明调用 Client 的指定 capability。"""
    method_spec = adapter.methods.get(capability)
    if method_spec is None:
        raise ValueError(
            f"adapter {adapter.name!r} 不支持 capability={capability!r} "
            f"(has: {sorted(adapter.capabilities)})"
        )
    client_cls = adapter.client_loader()
    native_kwargs = adapter.resolve_params(method_spec, **unified_kwargs)
    async with client_cls() as client:
        return await getattr(client, method_spec.method_name)(**native_kwargs)


async def _search_source(name: str, coro: Any) -> SearchResponse | None:
    """异常安全执行单源搜索。"""
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
    timeout = float(get_config().timeout)
    return max(1.0, min(timeout, _SEARCH_SOURCE_TIMEOUT_CAP_SECONDS))


async def _search_source_limited(name: str, coro: Any) -> SearchResponse | None:
    """带并发度限制 + 超时保护的搜索执行。"""
    async with get_semaphore("search"):
        timeout = _get_source_timeout_seconds()
        try:
            return await asyncio.wait_for(_search_source(name, coro), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s 搜索超时，已跳过 (%.1fs)", name, timeout)
            return None


def _select_adapters(
    domain: str,
    capability: str,
    sources: list[str] | None,
) -> list[SourceAdapter]:
    """根据用户给定的 sources 选出要调度的 adapter。"""
    if sources is None:
        names = defaults_for(domain, capability)
        if not names:
            logger.warning(
                "defaults_for(%s, %s) 为空；请在 registry/sources.py 声明 default_for",
                domain,
                capability,
            )
            return []
    else:
        names = list(sources)

    selected: list[SourceAdapter] = []
    for name in names:
        adapter = _registry_get(name)
        if adapter is None:
            logger.warning("未知数据源: %s，跳过", name)
            continue
        if domain not in adapter.domains:
            logger.warning(
                "%s domain=%s 与请求 domain=%s 不匹配，跳过",
                name,
                adapter.domain,
                domain,
            )
            continue
        if capability not in adapter.capabilities:
            logger.warning(
                "%s 不支持 capability=%s（有: %s），跳过",
                name,
                capability,
                sorted(adapter.capabilities),
            )
            continue
        selected.append(adapter)
    return selected


async def _execute_search(
    domain: str,
    query: str,
    adapters: list[SourceAdapter],
    limit: int,
    capability: str,
    **kwargs: Any,
) -> list[SearchResponse]:
    """统一的并发搜索执行。"""
    cfg = get_config()
    tasks: list[tuple[str, Any]] = []
    for adapter in adapters:
        if not cfg.is_source_enabled(adapter.name):
            logger.info("数据源 %s 已禁用，跳过", adapter.name)
            continue
        coro = _run_via_adapter(adapter, capability, query=query, limit=limit, **kwargs)
        tasks.append((adapter.name, coro))

    results = await asyncio.gather(
        *[_search_source_limited(n, coro) for n, coro in tasks],
    )
    responses = [r for r in results if isinstance(r, SearchResponse)]
    logger.info(
        "%s/%s 完成: %d/%d 源成功 (query=%s)",
        domain,
        capability,
        len(responses),
        len(tasks),
        query,
    )
    return responses


# ── 公开 API ───────────────────────────────────────────────


async def search(
    query: str,
    domain: str = "paper",
    capability: str = "search",
    sources: list[str] | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """v1 主搜索入口：按 (domain, capability) 派发。

    Args:
        query: 搜索关键词
        domain: 'paper' | 'patent' | 'web' | 'social' | 'video' | 'knowledge' |
                'developer' | 'cn_tech' | 'office' | 'archive'
        capability: 'search' | 'search_news' | 'search_images' | 'search_videos' |
                    'search_articles' | 'search_users' | ...
        sources: 指定源列表；None 表示用 registry 声明的默认源
        limit: 每个源返回的最多结果数
        **kwargs: 透传到各 Client

    Returns:
        每个成功源一个 SearchResponse（失败源会被跳过）
    """
    adapters = _select_adapters(domain, capability, sources)
    return await _execute_search(domain, query, adapters, limit, capability, **kwargs)


async def search_domain(
    query: str,
    domain: str,
    capability: str = "search",
    sources: list[str] | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """search() 的语义化别名，显式要求传 domain。"""
    return await search(query, domain, capability, sources, limit, **kwargs)


async def search_by_capability(
    query: str,
    capability: str,
    sources: list[str] | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """忽略 domain，对所有支持该 capability 的源派发。

    谨慎使用：会跨多个 domain 返回混合结果。一般建议用 search_all。
    """
    from souwen.registry import by_capability

    if sources is None:
        adapters = by_capability(capability)
    else:
        adapters = [
            a
            for a in (_registry_get(n) for n in sources)
            if a is not None and capability in a.capabilities
        ]
    cfg = get_config()
    tasks: list[tuple[str, Any]] = []
    for adapter in adapters:
        if not cfg.is_source_enabled(adapter.name):
            continue
        tasks.append(
            (
                adapter.name,
                _run_via_adapter(adapter, capability, query=query, limit=limit, **kwargs),
            )
        )
    results = await asyncio.gather(
        *[_search_source_limited(n, coro) for n, coro in tasks],
    )
    return [r for r in results if isinstance(r, SearchResponse)]


# ── 便捷 API ────────────────────────────────────────────


async def search_papers(
    query: str,
    sources: list[str] | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """并发多源论文搜索。"""
    return await search(query, "paper", "search", sources, per_page, **kwargs)


async def search_patents(
    query: str,
    sources: list[str] | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """并发多源专利搜索。"""
    return await search(query, "patent", "search", sources, per_page, **kwargs)
