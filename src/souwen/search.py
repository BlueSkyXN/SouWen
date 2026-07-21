"""SouWen 统一搜索门面 — 从注册表派生

源调度由 `souwen.registry` 派生。对外函数签名：

    search(query, domain="paper", **kwargs) → list[Any]
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
import inspect
import logging
from typing import Any

from souwen.config import get_config
from souwen.core.concurrency import get_semaphore
from souwen.editions import EditionError, ensure_source_allowed
from souwen.models import SearchResponse
from souwen.registry import (
    all_adapters,
    all_domains,
    by_capability,
    defaults_for,
    get as _registry_get,
)
from souwen.registry.adapter import MethodSpec, SourceAdapter

# ── Web 搜索 ───────────────────────────────────────────────
from souwen.web.search import web_search  # re-export

logger = logging.getLogger("souwen.search")
_SEARCH_SOURCE_TIMEOUT_CAP_SECONDS = 15.0
_QUERYLESS_CAPABILITIES = frozenset({"get_trending"})
_QUERY_PARAMETER_CANDIDATES: dict[str, tuple[str, ...]] = {
    "search": ("query", "keyword"),
    "search_news": ("query", "keyword"),
    "search_images": ("query", "keyword"),
    "search_videos": ("query", "keyword"),
    "search_articles": ("query", "keyword"),
    "search_users": ("query", "keyword"),
    "archive_lookup": ("url",),
    "archive_save": ("url",),
    "fetch": ("url", "urls", "paper_id", "url_or_shorthand"),
    "get_detail": ("video_id", "video_ids", "bvid", "id"),
    "get_transcript": ("video_id",),
    "exa:find_similar": ("url",),
    "unpaywall:find_oa": ("doi",),
    "opencitations:citation_count": ("identifier",),
    "opencitations:citations": ("identifier",),
    "opencitations:references": ("identifier",),
}
_DEFAULT_QUERY_PARAMETER_CANDIDATES = (
    "query",
    "keyword",
    "url",
    "urls",
    "doi",
    "paper_id",
    "url_or_shorthand",
    "video_id",
    "video_ids",
    "bvid",
    "identifier",
)
_LIST_QUERY_PARAMETERS = frozenset({"urls", "video_ids"})


def _normalize_source_names(value: object, *, name: str) -> list[str] | None:
    """Normalize optional string-or-sequence name arguments."""
    if value is None:
        return None
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list | tuple):
        items = list(value)
    else:
        raise ValueError(f"{name} 必须是字符串、字符串列表或 None")

    normalized: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{name} 必须是非空字符串、非空字符串列表或 None")
        normalized.append(item.strip())
    return normalized


def _normalize_query_text(value: object, *, name: str = "query") -> str:
    """Normalize public search query text before provider dispatch."""
    if not isinstance(value, str):
        raise ValueError(f"{name} 必须是非空字符串")
    query = value.strip()
    if not query:
        raise ValueError(f"{name} 必须是非空字符串")
    return query


# ── 通用客户端执行器 ───────────────────────────────────────


async def _run_via_adapter(
    adapter: SourceAdapter,
    capability: str,
    /,
    **unified_kwargs: Any,
) -> Any:
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


async def _search_source(name: str, coro: Any) -> Any | None:
    """执行单个数据源搜索（异常安全）

    捕获和处理异常，区分类型：
      - ConfigError: 缺失配置，info 跳过
      - RateLimitError: 被限流，warning 但不抛出
      - 其他异常：warning 但不阻止其他源继续执行

    Args:
        name: 数据源名称（用于日志）
        coro: 异步协程（通常是 `_run_via_adapter(...)`）

    Returns:
        Client 方法返回值或 None（失败时）
    """
    try:
        return await coro
    except Exception as e:
        from souwen.core.exceptions import LocalCatalogUnavailableError

        if isinstance(e, LocalCatalogUnavailableError):
            raise
        from souwen.core.exceptions import ConfigError, RateLimitError

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


async def _search_source_limited(name: str, coro: Any) -> Any | None:
    """带并发度限制 + 超时保护的搜索执行。"""
    async with get_semaphore("search"):
        timeout = _get_source_timeout_seconds()
        try:
            return await asyncio.wait_for(_search_source(name, coro), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s 搜索超时，已跳过 (%.1fs)", name, timeout)
            return None


def _build_capability_kwargs(
    adapter: SourceAdapter,
    capability: str,
    query: str,
    limit: int,
    extra_kwargs: dict[str, Any],
) -> dict[str, Any]:
    """按 capability 组装统一参数，避免把搜索参数硬塞给非搜索方法。"""
    unified: dict[str, Any] = dict(extra_kwargs)
    method_spec = adapter.methods.get(capability)
    if method_spec is None:
        unified.setdefault("query", query)
        unified.setdefault("limit", limit)
        return unified

    parameter_names, accepts_var_keyword = _get_method_parameters(adapter, method_spec)
    limit_param = method_spec.param_map.get("limit", "limit")
    if "limit" not in unified and limit_param not in unified:
        if accepts_var_keyword or limit_param in parameter_names:
            unified["limit"] = limit

    if capability in _QUERYLESS_CAPABILITIES:
        return unified

    candidates = _QUERY_PARAMETER_CANDIDATES.get(capability, _DEFAULT_QUERY_PARAMETER_CANDIDATES)
    if _has_explicit_query_argument(unified, method_spec, candidates):
        return unified

    query_param = _select_query_parameter(
        method_spec, parameter_names, accepts_var_keyword, candidates
    )
    if query_param is not None:
        unified[query_param] = _coerce_query_value(query_param, query)
        return unified

    unified.setdefault("query", query)
    return unified


def _get_method_parameters(
    adapter: SourceAdapter,
    method_spec: MethodSpec,
) -> tuple[set[str], bool]:
    """返回目标方法参数名；无法检查时退回到宽松透传。"""
    try:
        client_cls = adapter.client_loader()
        method = getattr(client_cls, method_spec.method_name)
        signature = inspect.signature(method)
    except (AttributeError, TypeError, ValueError):
        return set(), True

    parameters = signature.parameters.values()
    names = {param.name for param in parameters}
    accepts_var_keyword = any(param.kind is inspect.Parameter.VAR_KEYWORD for param in parameters)
    return names, accepts_var_keyword


def _has_explicit_query_argument(
    unified: dict[str, Any],
    method_spec: MethodSpec,
    candidates: tuple[str, ...],
) -> bool:
    names = set(candidates) | {"query"}
    names.update(method_spec.param_map.get(name, name) for name in candidates)
    return any(name in unified for name in names)


def _select_query_parameter(
    method_spec: MethodSpec,
    parameter_names: set[str],
    accepts_var_keyword: bool,
    candidates: tuple[str, ...],
) -> str | None:
    if "query" in method_spec.param_map:
        return "query"
    for candidate in candidates:
        native_name = method_spec.param_map.get(candidate, candidate)
        if accepts_var_keyword or native_name in parameter_names:
            return candidate
    return None


def _coerce_query_value(parameter_name: str, query: str) -> Any:
    if parameter_name not in _LIST_QUERY_PARAMETERS:
        return query
    if isinstance(query, list):
        return query
    if isinstance(query, tuple):
        return list(query)
    return [query]


def _is_adapter_allowed_by_edition(
    adapter: SourceAdapter,
    *,
    edition: str,
    explicit: bool,
) -> bool:
    """Return whether an adapter may run in the current edition."""
    try:
        ensure_source_allowed(adapter, edition)
    except EditionError as exc:
        if explicit:
            raise
        logger.info("数据源 %s 不在 edition=%s 中，跳过: %s", adapter.name, edition, exc)
        return False
    return True


# ── 域派发（paper / patent）────────────────────────────────


def _select_adapters(
    domain: str,
    capability: str,
    sources: list[str] | str | None,
) -> list[SourceAdapter]:
    """根据用户给定的 sources（可为 None）选出实际要调度的 adapter。

    规则：
      1. sources=None → 用 `defaults_for(domain, capability)`
      2. 未知 name → 记 warning 跳过
      3. adapter.domain 必须匹配（或 domain 在 extra_domains 里）
      4. adapter.capabilities 必须含 capability
    """
    selected_sources = _normalize_source_names(sources, name="sources")
    explicit_sources = selected_sources is not None
    if selected_sources is None:
        names = defaults_for(domain, capability)
        if not names:
            logger.warning(
                "defaults_for(%s, %s) 为空；请在 registry/sources/ 声明 default_for",
                domain,
                capability,
            )
            return []
    else:
        names = selected_sources

    cfg = get_config()
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
        if not _is_adapter_allowed_by_edition(
            adapter,
            edition=cfg.edition,
            explicit=explicit_sources,
        ):
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
) -> list[Any]:
    """统一的并发 capability 执行：跑 `_search_source_limited` on each adapter。"""
    from souwen.core.exceptions import LocalCatalogUnavailableError

    cfg = get_config()
    tasks: list[tuple[str, Any]] = []
    for adapter in adapters:
        if not cfg.is_source_enabled(adapter.name, default=adapter.runtime_default_enabled):
            logger.info("数据源 %s 已禁用，跳过", adapter.name)
            continue
        unified_kwargs = _build_capability_kwargs(adapter, capability, query, limit, kwargs)
        coro = _run_via_adapter(adapter, capability, **unified_kwargs)
        tasks.append((adapter.name, coro))

    results = await asyncio.gather(
        *[_search_source_limited(n, coro) for n, coro in tasks], return_exceptions=True
    )
    local_failures = [item for item in results if isinstance(item, LocalCatalogUnavailableError)]
    if local_failures and len(tasks) == 1:
        raise local_failures[0]
    for failure in local_failures:
        logger.warning("local catalog source unavailable: %s", failure)
    responses = [r for r in results if r is not None and not isinstance(r, Exception)]
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
    sources: list[str] | str | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """并发多源论文搜索。

    Args:
        query: 搜索关键词
        sources: 数据源或数据源列表；字符串会归一化为单元素列表；None 表示使用
            registry 的默认源（由 adapter.default_for 声明）
        per_page: 每个源返回的结果数
        **kwargs: 额外参数透传到各 Client 的 search 方法（注意：走 adapter.param_map
            翻译，源原生参数名可以用 extra_domains 时的 param_map）

    Returns:
        每个数据源一个 SearchResponse 的列表
    """
    query = _normalize_query_text(query)
    return await search(
        query,
        domain="paper",
        capability="search",
        sources=sources,
        limit=per_page,
        **kwargs,
    )


async def search_books(
    query: str,
    sources: list[str] | str | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """Search work-level book catalog records through the registry."""
    query = _normalize_query_text(query)
    return await search(
        query,
        domain="book",
        capability="search",
        sources=sources,
        limit=per_page,
        **kwargs,
    )


async def search_research_outputs(
    query: str,
    sources: list[str] | str | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """Search datasets, software and other non-paper research outputs through the registry."""
    query = _normalize_query_text(query)
    return await search(
        query,
        domain="research_output",
        capability="search",
        sources=sources,
        limit=per_page,
        **kwargs,
    )


async def search_patents(
    query: str,
    sources: list[str] | str | None = None,
    per_page: int = 10,
    **kwargs: Any,
) -> list[SearchResponse]:
    """并发多源专利搜索。

    Args:
        query: 搜索关键词
        sources: 数据源或数据源列表；字符串会归一化为单元素列表；None 表示使用
            registry 的默认专利源
        per_page: 每个源返回的结果数
        **kwargs: 额外参数

    Returns:
        每个数据源一个 SearchResponse 的列表
    """
    query = _normalize_query_text(query)
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
    sources: list[str] | str | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> list[Any]:
    """统一搜索/能力入口 — 根据 (domain, capability) 从 registry 派发。

    Args:
        query: 搜索关键词
        domain: 搜索领域，如 "paper" | "patent" | "web" | "social"
        capability: 能力名，如 "search" | "search_news" | "search_images"
        sources: 指定源或源列表；字符串会归一化为单元素列表；None 表示使用
            registry 声明的默认源
        limit: 每个源返回的结果数量
        **kwargs: 透传到各 Client
    """
    query = _normalize_query_text(query)
    if domain not in all_domains():
        supported = " | ".join(all_domains())
        raise ValueError(f"未知搜索领域: {domain!r}，支持 {supported}")
    adapters = _select_adapters(domain, capability, sources)
    return await _execute_search(domain, query, adapters, limit, capability, **kwargs)


async def search_domain(
    query: str,
    domain: str,
    capability: str = "search",
    sources: list[str] | str | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> list[Any]:
    """`search()` 的语义化别名，显式要求传 domain。"""
    query = _normalize_query_text(query)
    return await search(query, domain, capability, sources, limit, **kwargs)


async def search_by_capability(
    query: str,
    capability: str,
    sources: list[str] | str | None = None,
    limit: int = 10,
    **kwargs: Any,
) -> list[Any]:
    """忽略 domain，对所有支持某 capability 的源派发。"""
    query = _normalize_query_text(query)
    selected_sources = _normalize_source_names(sources, name="sources")
    if selected_sources is None:
        cfg = get_config()
        adapters = [
            adapter
            for adapter in by_capability(capability)
            if _is_adapter_allowed_by_edition(
                adapter,
                edition=cfg.edition,
                explicit=False,
            )
        ]
    else:
        cfg = get_config()
        adapters = []
        for name in selected_sources:
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
            if not _is_adapter_allowed_by_edition(
                adapter,
                edition=cfg.edition,
                explicit=True,
            ):
                continue
            adapters.append(adapter)
    return await _execute_search("*", query, adapters, limit, capability, **kwargs)


DEFAULT_AGGREGATE_DOMAINS: tuple[str, ...] = ("paper", "web", "knowledge", "developer")


async def search_all(
    query: str,
    domains: list[str] | str | None = None,
    per_domain_limit: int = 5,
    timeout: float | None = None,
    **kwargs: Any,
) -> dict[str, list[SearchResponse]]:
    """跨多个 domain 并行搜索，按 domain 分组返回。

    ``domains`` 可传单个 domain 字符串或字符串列表；None 和空列表沿用默认聚合域。
    """
    query = _normalize_query_text(query)
    if "limit" in kwargs:
        alias_limit = kwargs.pop("limit")
        if per_domain_limit != 5 and alias_limit != per_domain_limit:
            raise ValueError("search_all() 不应同时传入不同的 per_domain_limit 和 limit")
        per_domain_limit = int(alias_limit)

    selected_domains = _normalize_source_names(domains, name="domains")
    selected = selected_domains if selected_domains else list(DEFAULT_AGGREGATE_DOMAINS)
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


def _default_book_sources() -> list[str]:
    """默认图书源列表（从 registry 派生）。"""
    return defaults_for("book", "search")


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
    "search_books",
    "search_research_outputs",
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
