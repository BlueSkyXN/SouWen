"""SouWen 统一搜索门面 — 从注册表派生

源调度由 `souwen.registry` 派生。对外函数签名：

    search(query, domain="paper", **kwargs) → list[SearchResponse]
    search_papers(query, sources=None, per_page=10, **kwargs) → list[SearchResponse]
    search_patents(query, sources=None, per_page=10, **kwargs) → list[SearchResponse]
    web_search                              —— 从 souwen.web.search re-export

默认源来源：
    `registry.views.defaults_for(domain, "search")`（由 adapter.default_for 声明，D9）

并发策略：
    - asyncio.gather 并发
    - 单源超时（<= 15s；受 SouWenConfig.timeout 约束）
    - 全局并发度 Semaphore（10，可 SOUWEN_MAX_CONCURRENCY 覆盖）
    - **Semaphore 改用 ContextVar**（D12；见 `souwen.core.concurrency`）

模块依赖：
    - souwen.config —— 配置读取
    - souwen.models —— SearchResponse
    - souwen.registry —— 数据源注册表（派生 Client / MethodSpec）
    - souwen.core.concurrency —— 并发度信号量
    - souwen.web.search —— web_search re-export
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from souwen.config import get_config
from souwen.core.concurrency import get_semaphore
from souwen.models import SearchResponse
from souwen.registry import (
    all_adapters,
    all_domains,
    by_capability,
    defaults_for,
    get as _registry_get,
)
from souwen.registry.adapter import SourceAdapter

# ── Web 搜索 ───────────────────────────────────────────────
from souwen.web.search import web_search  # re-export

logger = logging.getLogger("souwen.search")
_SEARCH_SOURCE_TIMEOUT_CAP_SECONDS = 15.0


# ── 通用客户端执行器 ───────────────────────────────────────


async def _run_via_adapter(
    adapter: SourceAdapter,
    capability: str,
    /,
    **unified_kwargs: Any,
) -> SearchResponse:
    """按 adapter 声明调用 Client。

    执行顺序：
      1. `adapter.client_loader()` 懒加载类（首次）
      2. `adapter.methods[capability]` 取 MethodSpec
      3. `adapter.resolve_params(...)` 把统一入参翻译为原生参数
      4. `async with client: client.<method>(**native)` 实际调用
    """
    method_spec = adapter.methods.get(capability)
    if method_spec is None:
        raise ValueError(
            f"adapter {adapter.name!r} 不支持 capability={capability!r} "
            f"(has: {sorted(adapter.capabilities)})"
        )
    client_cls = adapter.client_loader()
    native_kwargs = adapter.resolve_params(method_spec, **unified_kwargs)
    method = method_spec.method_name
    async with client_cls() as client:
        return await getattr(client, method)(**native_kwargs)


async def _search_source(name: str, coro: Any) -> SearchResponse | None:
    """执行单个数据源搜索（异常安全）

    捕获和处理异常，区分类型：
      - ConfigError: 缺失配置，info 跳过
      - RateLimitError: 被限流，warning 但不抛出
      - 其他异常：warning 但不阻止其他源继续执行

    Args:
        name: 数据源名称（用于日志）
        coro: 异步协程（通常是 `_run_via_adapter(adapter, "search", query=..., limit=...)`）

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


async def _search_source_limited(name: str, coro: Any) -> SearchResponse | None:
    """带并发度限制 + 超时保护的搜索执行。"""
    async with get_semaphore("search"):
        timeout = _get_source_timeout_seconds()
        try:
            return await asyncio.wait_for(_search_source(name, coro), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s 搜索超时，已跳过 (%.1fs)", name, timeout)
            return None


# ── 域派发（paper / patent）────────────────────────────────


def _select_adapters(
    domain: str,
    capability: str,
    sources: list[str] | None,
) -> list[SourceAdapter]:
    """根据用户给定的 sources（可为 None）选出实际要调度的 adapter。

    规则：
      1. sources=None → 用 `defaults_for(domain, capability)`
      2. 未知 name → 记 warning 跳过
      3. adapter.domain 必须匹配（或 domain 在 extra_domains 里）
      4. adapter.capabilities 必须含 capability
    """
    if sources is None:
        names = defaults_for(domain, capability)
        if not names:
            logger.warning(
                "defaults_for(%s, %s) 为空；请在 registry/sources/ 声明 default_for",
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
                "数据源 %s domain=%s 与请求 domain=%s 不匹配，跳过",
                name,
                adapter.domain,
                domain,
            )
            continue
        if capability not in adapter.capabilities:
            logger.warning(
                "数据源 %s 不支持 capability=%s (有: %s)，跳过",
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
    capability: str = "search",
    **kwargs: Any,
) -> list[SearchResponse]:
    """统一的并发搜索执行：跑 `_search_source_limited` on each adapter。"""
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
        "%s/%s 搜索完成: %d/%d 源成功 (query=%s)",
        domain,
        capability,
        len(responses),
        len(tasks),
        query,
    )
    return responses


# ── 公开 API ────────────────────────────────────────────


async def search_papers(
    query: str,
    sources: list[str] | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """并发多源论文搜索。

    Args:
        query: 搜索关键词
        sources: 数据源列表；None 表示使用 registry 的默认源（由 adapter.default_for 声明）
        per_page: 每个源返回的结果数
        **kwargs: 额外参数透传到各 Client 的 search 方法（注意：走 adapter.param_map
            翻译，源原生参数名可以用 extra_domains 时的 param_map）

    Returns:
        每个数据源一个 SearchResponse 的列表
    """
    return await search(
        query,
        domain="paper",
        capability="search",
        sources=sources,
        limit=per_page,
        **kwargs,
    )


async def search_patents(
    query: str,
    sources: list[str] | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """并发多源专利搜索。

    Args:
        query: 搜索关键词
        sources: 数据源列表；None 表示使用 registry 的默认源（默认 ["google_patents"]）
        per_page: 每个源返回的结果数
        **kwargs: 额外参数

    Returns:
        每个数据源一个 SearchResponse 的列表
    """
    return await search(
        query,
        domain="patent",
        capability="search",
        sources=sources,
        limit=per_page,
        **kwargs,
    )


async def search(
    query: str,
    domain: str = "paper",
    capability: str = "search",
    sources: list[str] | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """统一搜索入口 — 根据 (domain, capability) 从 registry 派发。

    Args:
        query: 搜索关键词
        domain: 搜索领域，如 "paper" | "patent" | "web" | "social"
        capability: 能力名，如 "search" | "search_news" | "search_images"
        sources: 指定源列表；None 表示使用 registry 声明的默认源
        limit: 每个源返回的结果数量
        **kwargs: 透传到各 Client
    """
    if domain not in all_domains():
        supported = " | ".join(all_domains())
        raise ValueError(f"未知搜索领域: {domain!r}，支持 {supported}")
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
    """`search()` 的语义化别名，显式要求传 domain。"""
    return await search(query, domain, capability, sources, limit, **kwargs)


async def search_by_capability(
    query: str,
    capability: str,
    sources: list[str] | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """忽略 domain，对所有支持某 capability 的源派发。"""
    if sources is None:
        adapters = by_capability(capability)
    else:
        adapters = []
        for name in sources:
            adapter = _registry_get(name)
            if adapter is None:
                logger.warning("未知数据源: %s，跳过", name)
                continue
            if capability not in adapter.capabilities:
                logger.warning(
                    "%s 不支持 capability=%s（有: %s），跳过",
                    name,
                    capability,
                    sorted(adapter.capabilities),
                )
                continue
            adapters.append(adapter)
    return await _execute_search("*", query, adapters, limit, capability, **kwargs)


DEFAULT_AGGREGATE_DOMAINS: tuple[str, ...] = ("paper", "web", "knowledge", "developer")


async def search_all(
    query: str,
    domains: list[str] | None = None,
    per_domain_limit: int = 5,
    timeout: float | None = None,
    **kwargs: Any,
) -> dict[str, list[SearchResponse]]:
    """跨多个 domain 并行搜索，按 domain 分组返回。"""
    selected = list(domains) if domains else list(DEFAULT_AGGREGATE_DOMAINS)
    results: dict[str, list[SearchResponse]] = {}

    async def _run_one(domain: str) -> tuple[str, list[SearchResponse]]:
        try:
            coro = search(query, domain=domain, limit=per_domain_limit, **kwargs)
            if timeout is not None:
                return domain, await asyncio.wait_for(coro, timeout=timeout)
            return domain, await coro
        except asyncio.TimeoutError:
            logger.warning("search_all: domain=%s 超时（%.1fs）", domain, timeout or 0)
            return domain, []
        except Exception as exc:
            logger.warning(
                "search_all: domain=%s 失败 [%s]: %s",
                domain,
                type(exc).__name__,
                exc,
            )
            return domain, []

    pairs = await asyncio.gather(*[_run_one(domain) for domain in selected])
    for domain, response in pairs:
        results[domain] = response
    return results


# ── 内部辅助：默认源派生（保留私有名字便于测试 mock/patch）─────


def _default_paper_sources() -> list[str]:
    """默认论文源列表（从 registry 派生）。"""
    return defaults_for("paper", "search")


def _default_patent_sources() -> list[str]:
    """默认专利源列表（从 registry 派生）。"""
    return defaults_for("patent", "search")


# ── 为测试方便保留的入口 ───────────────────────────────────


def _get_max_concurrency() -> int:
    """便捷入口（重定向到 core.concurrency）。"""
    from souwen.core.concurrency import get_max_concurrency

    return get_max_concurrency()


def _get_semaphore() -> asyncio.Semaphore:
    """便捷入口（重定向到 core.concurrency）。"""
    return get_semaphore("search")


# 公开给外部用户的符号
__all__ = [
    "search",
    "search_domain",
    "search_by_capability",
    "search_all",
    "search_papers",
    "search_patents",
    "web_search",
]


# ── 调试友好：一次性 eager 收集注册表里的默认源名 ────────────
# 不影响懒加载：只读 adapter.name / default_for，不调 client_loader。
def _debug_dump_defaults() -> dict[str, list[str]]:
    """内部：返回每个 (domain, capability) 的默认源名清单。"""
    triples: dict[str, list[str]] = {}
    for adapter in all_adapters().values():
        for key in adapter.default_for:
            triples.setdefault(key, []).append(adapter.name)
    return triples
