"""并发多引擎聚合搜索

文件用途：
    核心网页搜索聚合模块。支持 22+ 搜索引擎（爬虫、API、元搜索混合），
    通过 asyncio 并发查询、聚合结果、URL 去重，为用户提供统一搜索接口。

函数/类清单：
    _search_engine(engine_cls, query, max_results, **kwargs) -> list[WebSearchResult]
        - 功能：执行单个引擎的搜索（异常安全 + 超时控制 + 并发度限制）
        - 输入：engine_cls (type) 引擎类, query (str) 搜索词, max_results (int) 最大结果数
        - 输出：list[WebSearchResult] 搜索结果列表，异常返回空列表
        - 关键变量：_WEB_ENGINE_TIMEOUT_CAP_SECONDS = 15.0 超时上限, _get_web_semaphore() 并发信号量

    _get_engine_timeout_seconds() -> float
        - 功能：从配置读取超时时间，取值范围 [1.0, 15.0] 秒
        - 输入：无
        - 输出：float 单个引擎的搜索超时秒数
        - 关键变量：_WEB_ENGINE_TIMEOUT_CAP_SECONDS = 15.0 上限

    _deduplicate(results: Sequence[WebSearchResult]) -> list[WebSearchResult]
        - 功能：按 URL 去重（规范化后的小写 URL），保留首次出现的结果
        - 输入：results 搜索结果序列
        - 输出：去重后的结果列表

    web_search(query, engines=None, max_results_per_engine=10, deduplicate=True, **kwargs) -> WebSearchResponse
        - 功能：并发查询多个搜索引擎，聚合并可选去重结果
        - 输入：query 搜索词, engines 引擎列表(默认 ["duckduckgo", "bing"]),
                max_results_per_engine 每引擎最大结果数, deduplicate 是否去重, **kwargs 引擎特定参数
        - 输出：WebSearchResponse 聚合响应对象
        - 关键变量：engine_map 引擎名->类映射, source_map 引擎名->SourceType 映射, selected 最终选用的引擎列表

模块依赖：
    - asyncio: 异步并发框架
    - logging: 日志记录
    - souwen.config: 配置读取（超时、引擎开启状态）
    - souwen.models: WebSearchResult, WebSearchResponse, SourceType 数据模型
    - souwen.web.*: 各个搜索引擎客户端（22+ 个）

技术要点：
    - asyncio.gather 并发（等价 Rust 的 FuturesUnordered + tokio::spawn）
    - 部分引擎失败不影响整体结果（return_exceptions=True）
    - URL 去重避免重复（规范化小写 + 去尾部斜杠）
    - 全局并发度限制（_get_web_semaphore()）确保不过载
"""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from souwen.config import get_config
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
from souwen.web.metaso import MetasoClient
from souwen.web.startpage import StartpageClient
from souwen.web.baidu import BaiduClient
from souwen.web.mojeek import MojeekClient
from souwen.web.yandex import YandexClient
from souwen.web.whoogle import WhoogleClient
from souwen.web.websurfx import WebsurfxClient
from souwen.web.github import GitHubClient
from souwen.web.stackoverflow import StackOverflowClient
from souwen.web.reddit import RedditClient
from souwen.web.bilibili import BilibiliClient
from souwen.web.wikipedia import WikipediaClient
from souwen.web.youtube import YouTubeClient
from souwen.web.zhihu import ZhihuClient
from souwen.web.weibo import WeiboClient
from souwen.web.csdn import CSDNClient
from souwen.web.juejin import JuejinClient
from souwen.web.linuxdo import LinuxDoClient

logger = logging.getLogger("souwen.web.search")
_WEB_ENGINE_TIMEOUT_CAP_SECONDS = 15.0


def _get_web_semaphore() -> asyncio.Semaphore:
    """返回与当前 running event loop 绑定的 Semaphore（per-loop 懒加载）

    避免在模块导入时创建 Semaphore，防止跨事件循环使用导致的错误。
    """
    loop = asyncio.get_running_loop()
    sem = getattr(loop, "_souwen_web_sem", None)
    if sem is None:
        sem = asyncio.Semaphore(10)
        loop._souwen_web_sem = sem  # type: ignore[attr-defined]
    return sem


async def _search_engine(
    engine_cls: type,
    query: str,
    max_results: int,
    **kwargs,
) -> list[WebSearchResult]:
    """搜索单个引擎（异常安全 + 并发度限制）

    执行单个搜索引擎的查询任务，在信号量保护下运行，限制并发度。
    所有异常（超时、网络错误、解析错误等）都被捕获，
    返回空列表以不中断其他引擎的搜索。

    Args:
        engine_cls: 引擎客户端类（如 DuckDuckGoClient）
        query: 搜索关键词
        max_results: 最大返回结果数
        **kwargs: 传递给引擎构造函数的参数

    Returns:
        list[WebSearchResult]: 搜索结果列表；异常时返回 []
    """
    timeout = _get_engine_timeout_seconds()

    async def _run() -> list[WebSearchResult]:
        # 创建引擎实例、执行搜索、返回结果列表
        async with engine_cls(**kwargs) as client:
            resp = await client.search(query, max_results=max_results)
            return list(resp.results)

    async with _get_web_semaphore():
        try:
            # 执行搜索任务，设置超时上限
            return await asyncio.wait_for(_run(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s 搜索超时，已跳过 (%.1fs)", engine_cls.__name__, timeout)
            return []
        except Exception as e:
            # 捕获所有异常（包括 API 错误、网络异常、解析错误等）
            logger.warning("%s 搜索失败 [%s]: %s", engine_cls.__name__, type(e).__name__, e)
            return []


def _get_engine_timeout_seconds() -> float:
    """单个 Web 引擎搜索超时（秒数）

    从配置读取超时时间，夹在 [1.0, 15.0] 之间确保合理范围。
    防止过短的超时导致引擎查询失败，也防止过长的超时拖累整体性能。

    Returns:
        float: 超时秒数，范围 [1.0, 15.0]
    """
    timeout = float(get_config().timeout)
    # 确保超时时间不超过上限、不少于 1 秒
    return max(1.0, min(timeout, _WEB_ENGINE_TIMEOUT_CAP_SECONDS))


def _deduplicate(results: Sequence[WebSearchResult]) -> list[WebSearchResult]:
    """URL 去重，保留首次出现的结果

    规范化 URL（小写、去尾部斜杠），按规范化 URL 去重。
    保留首次出现的结果，确保结果列表顺序不变。

    Args:
        results: 待去重的搜索结果序列

    Returns:
        list[WebSearchResult]: 去重后的结果列表
    """
    seen_urls: set[str] = set()
    deduped: list[WebSearchResult] = []
    for r in results:
        # 规范化 URL：转小写 + 去尾部斜杠，避免 http://example.com 和 http://example.com/ 被重复计算
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

    同时查询 DuckDuckGo、Bing（或指定子集），
    聚合结果并可选去重。

    Args:
        query: 搜索关键词
        engines: 引擎列表，默认 ["duckduckgo", "bing"]
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
    # 引擎名 -> 客户端类的映射，用于动态加载引擎
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
        "metaso": MetasoClient,
        # 自部署元搜索（需自建实例）
        "whoogle": WhoogleClient,
        "websurfx": WebsurfxClient,
        # 社交/平台搜索
        "github": GitHubClient,
        "stackoverflow": StackOverflowClient,
        "reddit": RedditClient,
        "bilibili": BilibiliClient,
        "wikipedia": WikipediaClient,
        "youtube": YouTubeClient,
        "zhihu": ZhihuClient,
        "weibo": WeiboClient,
        "csdn": CSDNClient,
        "juejin": JuejinClient,
        "linuxdo": LinuxDoClient,
    }

    # 引擎名 -> SourceType 的映射，用于标记结果来源
    source_map: dict[str, SourceType] = {
        "duckduckgo": SourceType.WEB_DUCKDUCKGO,
        "yahoo": SourceType.WEB_YAHOO,
        "brave": SourceType.WEB_BRAVE,
        "google": SourceType.WEB_GOOGLE,
        "bing": SourceType.WEB_BING,
        "searxng": SourceType.WEB_SEARXNG,
        "tavily": SourceType.WEB_TAVILY,
        "exa": SourceType.WEB_EXA,
        "serper": SourceType.WEB_SERPER,
        "brave_api": SourceType.WEB_BRAVE_API,
        "serpapi": SourceType.WEB_SERPAPI,
        "firecrawl": SourceType.WEB_FIRECRAWL,
        "perplexity": SourceType.WEB_PERPLEXITY,
        "linkup": SourceType.WEB_LINKUP,
        "scrapingdog": SourceType.WEB_SCRAPINGDOG,
        "metaso": SourceType.WEB_METASO,
        "startpage": SourceType.WEB_STARTPAGE,
        "baidu": SourceType.WEB_BAIDU,
        "mojeek": SourceType.WEB_MOJEEK,
        "yandex": SourceType.WEB_YANDEX,
        "whoogle": SourceType.WEB_WHOOGLE,
        "websurfx": SourceType.WEB_WEBSURFX,
        "github": SourceType.WEB_GITHUB,
        "stackoverflow": SourceType.WEB_STACKOVERFLOW,
        "reddit": SourceType.WEB_REDDIT,
        "bilibili": SourceType.WEB_BILIBILI,
        "wikipedia": SourceType.WEB_WIKIPEDIA,
        "youtube": SourceType.WEB_YOUTUBE,
        "zhihu": SourceType.WEB_ZHIHU,
        "weibo": SourceType.WEB_WEIBO,
        "csdn": SourceType.WEB_CSDN,
        "juejin": SourceType.WEB_JUEJIN,
        "linuxdo": SourceType.WEB_LINUXDO,
    }

    # 默认使用在当前零配置场景下更稳定的公开引擎组合
    selected = engines or ["duckduckgo", "bing"]

    tasks = []
    cfg = get_config()
    # 为每个选中的引擎创建搜索任务
    for name in selected:
        # 检查引擎是否在配置中被启用
        if not cfg.is_source_enabled(name):
            logger.info("引擎 %s 已禁用，跳过", name)
            continue
        # 获取对应的引擎类
        cls = engine_map.get(name)
        if cls is None:
            logger.warning("未知引擎: %s，跳过", name)
            continue
        # 添加到任务列表，后续并发执行
        tasks.append(_search_engine(cls, query, max_results_per_engine, **kwargs))

    # 并发执行所有引擎（等价 Rust 的 FuturesUnordered + tokio::spawn）
    # return_exceptions=True 确保单个引擎失败不阻塞整体任务
    engine_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: list[WebSearchResult] = []
    # 聚合来自各引擎的结果
    for result in engine_results:
        if isinstance(result, list):
            # 正常的搜索结果列表
            all_results.extend(result)
        elif isinstance(result, Exception):
            # 记录引擎的异常（虽然已在 _search_engine 中处理，这是额外的保障）
            logger.warning("引擎返回异常: %s", result)

    # 可选的 URL 去重
    if deduplicate:
        all_results = _deduplicate(all_results)

    logger.info(
        "聚合搜索完成: %d 条结果 (query=%s, engines=%s)",
        len(all_results),
        query,
        selected,
    )

    # 返回聚合响应，source 取第一个引擎的类型
    return WebSearchResponse(
        query=query,
        source=source_map.get(selected[0], SourceType.WEB_DUCKDUCKGO)
        if selected
        else SourceType.WEB_DUCKDUCKGO,
        results=all_results,
        total_results=len(all_results),
    )
