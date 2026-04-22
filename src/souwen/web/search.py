"""并发多引擎聚合搜索（从注册表派生）

文件用途：
    网页搜索聚合模块。引擎调度由 `souwen.registry` 派生：

    - 引擎类通过 registry 字符串懒加载（不再有手写 engine_map / source_map）
    - `SourceType` 标签由 adapter 名 → `SourceType` 的派生映射（见 `_source_type_for`）

公开函数签名：
    web_search(query, engines=None, max_results_per_engine=10, deduplicate=True, **kw)
      → WebSearchResponse

并发与超时策略：Semaphore 使用 ContextVar（D12；`souwen.core.concurrency`）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from souwen.config import get_config
from souwen.core.concurrency import get_semaphore
from souwen.models import SourceType, WebSearchResponse, WebSearchResult
from souwen.registry import get as _registry_get

logger = logging.getLogger("souwen.web.search")
_WEB_ENGINE_TIMEOUT_CAP_SECONDS = 15.0

# ── Registry 名字 → SourceType 枚举值的映射 ─────────────────
# 为 `WebSearchResponse.source` 字段提供 SourceType 标签。
# 允许跨 domain 的源（youtube / bilibili / reddit / github / stackoverflow /
# wikipedia / twitter / facebook / feishu_drive / zhihu / weibo / csdn / juejin / linuxdo），
# 以维持 web_search "可以点名任意已注册源" 的契约。
# 如果 `SourceType` 里找不到匹配项（如 archive / fetch-only 源），回退到 WEB_DUCKDUCKGO。


def _source_type_for(name: str) -> SourceType:
    """把 registry 里的 adapter.name 映射为 SourceType 枚举值。

    命名规则：
      - 爬虫/API 类网页引擎 → `WEB_{NAME_UPPER}`
      - DDG 变种 → `WEB_DDG_{VARIANT}`（ddg_news/images/videos）
      - paper/patent → 自身枚举（`OPENALEX` / `ARXIV` / ...）
      - fetch-only（builtin / jina_reader / ...）→ `FETCH_{NAME_UPPER}`
      - 未知源 → `WEB_DUCKDUCKGO` 作兜底

    该映射用于 `WebSearchResponse.source`——它只在 web 聚合入口返回时填充。
    """
    # 特殊重命名
    specials = {
        "duckduckgo_news": SourceType.WEB_DDG_NEWS,
        "duckduckgo_images": SourceType.WEB_DDG_IMAGES,
        "duckduckgo_videos": SourceType.WEB_DDG_VIDEOS,
        "zhipuai": SourceType.WEB_ZHIPUAI,
    }
    if name in specials:
        return specials[name]

    upper = name.upper()
    # 尝试 WEB_XXX
    try:
        return SourceType[f"WEB_{upper}"]
    except KeyError:
        pass
    # 尝试 FETCH_XXX
    try:
        return SourceType[f"FETCH_{upper}"]
    except KeyError:
        pass
    # 尝试直接枚举（论文/专利名）
    try:
        return SourceType[upper]
    except KeyError:
        pass
    return SourceType.WEB_DUCKDUCKGO


def _get_web_semaphore() -> asyncio.Semaphore:
    """返回 web 聚合门面的 Semaphore（与 `search` 门面互相独立，避免阻塞）。"""
    return get_semaphore("web")


async def _search_engine(
    engine_cls: type,
    query: str,
    max_results: int,
    **kwargs,
) -> list[WebSearchResult]:
    """搜索单个引擎（异常安全 + 并发度限制）

    Args:
        engine_cls: 引擎客户端类（懒加载后的真实类型）
        query: 搜索关键词
        max_results: 最大返回结果数
        **kwargs: 传递给引擎构造函数的参数

    Returns:
        list[WebSearchResult]: 搜索结果列表；异常时返回 []
    """
    timeout = _get_engine_timeout_seconds()

    async def _run() -> list[WebSearchResult]:
        async with engine_cls(**kwargs) as client:
            resp = await client.search(query, max_results=max_results)
            return list(resp.results)

    async with _get_web_semaphore():
        try:
            return await asyncio.wait_for(_run(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s 搜索超时，已跳过 (%.1fs)", engine_cls.__name__, timeout)
            return []
        except Exception as e:
            logger.warning("%s 搜索失败 [%s]: %s", engine_cls.__name__, type(e).__name__, e)
            return []


def _get_engine_timeout_seconds() -> float:
    """单个 Web 引擎搜索超时（秒数），受 [1.0, 15.0] 约束。"""
    timeout = float(get_config().timeout)
    return max(1.0, min(timeout, _WEB_ENGINE_TIMEOUT_CAP_SECONDS))


def _deduplicate(results: Sequence[WebSearchResult]) -> list[WebSearchResult]:
    """URL 去重，保留首次出现的结果。

    规范化：小写 + 去尾部斜杠。
    """
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

    同时查询多个搜索引擎（默认 ["duckduckgo", "bing"]），聚合结果并可选去重。
    Engine 通过 `souwen.registry` 懒加载，因此该函数调用时才会 import 对应客户端。

    备注：
      - 可选用任何 `registry` 中声明了 `search` capability 的源（含跨 domain 的源，
        如 `youtube` / `bilibili` / `github`）。
      - 源的默认启用状态遵从 `SouWenConfig.is_source_enabled`。

    Args:
        query: 搜索关键词
        engines: 引擎名列表，默认 ["duckduckgo", "bing"]
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
    selected = engines or ["duckduckgo", "bing"]

    tasks = []
    cfg = get_config()
    for name in selected:
        if not cfg.is_source_enabled(name):
            logger.info("引擎 %s 已禁用，跳过", name)
            continue
        adapter = _registry_get(name)
        if adapter is None:
            logger.warning("未知引擎: %s，跳过", name)
            continue
        # 必须支持 'search' capability 才能走 web_search
        if "search" not in adapter.capabilities:
            logger.warning(
                "引擎 %s 不支持 'search' capability (有: %s)，跳过",
                name,
                sorted(adapter.capabilities),
            )
            continue
        try:
            cls = adapter.client_loader()
        except ImportError as e:
            logger.warning("引擎 %s Client 加载失败: %s", name, e)
            continue
        tasks.append(_search_engine(cls, query, max_results_per_engine, **kwargs))

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

    # source 字段使用"第一个引擎"的 SourceType
    first = selected[0] if selected else None
    source_tag = _source_type_for(first) if first else SourceType.WEB_DUCKDUCKGO

    return WebSearchResponse(
        query=query,
        source=source_tag,
        results=all_results,
        total_results=len(all_results),
    )
