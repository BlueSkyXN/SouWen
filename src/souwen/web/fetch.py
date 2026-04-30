"""并发多提供者聚合内容抓取

文件用途：
    核心网页内容抓取聚合模块。支持 21 个提供者（内置抓取、Jina Reader、arXiv Fulltext、
    Tavily、Firecrawl、Exa、XCrawl、Crawl4AI、Scrapfly、Diffbot、ScrapingBee、ZenRows、
    ScraperAPI、Apify、Cloudflare Browser Rendering、Wayback Machine、
    newspaper4k、readability、MCP、site_crawler（多页 BFS 爬虫）、
    deepwiki（DeepWiki 文档抓取）），
    通过 asyncio 并发抓取、聚合结果，为用户提供统一内容提取接口。

函数/类清单：
    validate_fetch_url(url) -> tuple[bool, str]
        - 功能：SSRF 防护 URL 校验（仅允许 http/https，拒绝私有 IP）
        - 输入：url (str) 待校验的 URL
        - 输出：(is_valid, reason) 元组，校验失败时 reason 给出原因
        - 关键变量：parsed.scheme 协议, parsed.hostname 主机名, socket.getaddrinfo DNS 解析

    _fetch_with_provider(provider, urls, timeout) -> FetchResponse
        - 功能：调度指定提供者执行批量抓取，未知提供者返回失败结果集
        - 输入：provider 提供者名称, urls URL 列表, timeout 单 URL 超时秒数
        - 输出：FetchResponse 聚合响应
        - 关键变量：分支 jina_reader / arxiv_fulltext / tavily / firecrawl / exa /
                    crawl4ai / scrapfly / diffbot / scrapingbee / zenrows /
                    scraperapi / apify / cloudflare / wayback / newspaper / readability

    fetch_content(urls, providers=None, timeout=30.0, skip_ssrf_check=False) -> FetchResponse
        - 功能：并发多提供者聚合抓取入口（用户显式选择提供者，不自动级联）
        - 输入：urls 目标 URL 列表, providers 提供者列表(默认 ["builtin"]),
                timeout 每 URL 超时, skip_ssrf_check 是否跳过 SSRF 校验
        - 输出：FetchResponse 聚合结果（含 SSRF 拦截记录）
        - 关键变量：selected 选用的提供者列表, valid_urls SSRF 通过的 URL,
                ssrf_failures SSRF 拦截的失败结果

模块依赖：
    - asyncio: 异步并发与超时控制
    - ipaddress: IP 地址类型判定（私有/回环/链路本地/保留）
    - socket: DNS 解析（getaddrinfo）
    - logging: 日志记录
    - souwen.config: 配置读取（API Key）
    - souwen.models: FetchResult, FetchResponse 数据模型
    - souwen.web.jina_reader / tavily / firecrawl / exa / crawl4ai_fetcher / scrapfly /
      diffbot / scrapingbee / zenrows / scraperapi / apify / cloudflare_browser /
      wayback / newspaper_fetcher / readability_fetcher: 各提供者客户端（懒加载）

技术要点：
    - SSRF 防护：解析 DNS 后逐个 IP 校验，拒绝私有/回环/链路本地/保留段
    - 提供者懒加载：在分支内 import，避免循环依赖与不必要的依赖加载
    - 用户显式选择提供者：默认 builtin（内置，零配置），可选 jina_reader 等付费提供者
    - 全局超时 = per-URL timeout + 10 秒宽限期
"""

from __future__ import annotations

import asyncio
import contextvars
import ipaddress
import logging
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from souwen.config import get_config
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.fetch")


FetchHandler = Callable[..., Awaitable[FetchResponse]]
"""Fetch handler signature: ``async (urls: list[str], timeout: float, **kwargs) -> FetchResponse``."""

# ── 插件上下文：由 plugin.py 加载器在 ep.load() 周围设置 ──
_current_plugin_owner: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "souwen_current_plugin_owner", default=None
)


@dataclass(frozen=True)
class _HandlerEntry:
    """fetch handler + 来源归属。"""

    handler: FetchHandler
    owner: str | None  # None = 内置 / 未知来源


_FETCH_HANDLERS: dict[str, _HandlerEntry] = {}


def register_fetch_handler(
    provider: str,
    handler: FetchHandler,
    *,
    override: bool = False,
    owner: str | None = None,
) -> bool:
    """注册某个 provider 的抓取处理函数。

    Args:
        provider: Provider name (must match registry SourceAdapter name)
        handler: Async callable ``(urls, timeout, **kwargs) -> FetchResponse``
        override: If True, allows overriding existing handlers
        owner: 注册来源插件名。为 None 时自动从 contextvar 读取（内置为 None）。

    Returns:
        True 表示注册成功；False 表示已存在且未 override。
    """
    effective_owner = owner if owner is not None else _current_plugin_owner.get()
    existing = _FETCH_HANDLERS.get(provider)
    if existing is not None and not override:
        logger.debug(
            "Fetch handler %r already registered by %r, skipping (new owner=%r)",
            provider,
            existing.owner,
            effective_owner,
        )
        return False
    _FETCH_HANDLERS[provider] = _HandlerEntry(handler=handler, owner=effective_owner)
    logger.debug(
        "Registered fetch handler: %s (owner=%s)",
        provider,
        effective_owner,
        extra={
            "event": "fetch_handler_registered",
            "plugin": effective_owner,
            "provider": provider,
        },
    )
    return True


def unregister_fetch_handlers_by_owner(owner: str) -> list[str]:
    """移除指定插件注册的所有 fetch handler。返回被移除的 provider 名列表。"""
    removed = [p for p, e in _FETCH_HANDLERS.items() if e.owner == owner]
    for p in removed:
        del _FETCH_HANDLERS[p]
    if removed:
        logger.info("已移除插件 %r 注册的 fetch handler: %s", owner, ", ".join(removed))
    return removed


def unregister_fetch_handler(provider: str) -> bool:
    """移除指定 provider 名的 fetch handler。返回是否有移除。"""
    if provider in _FETCH_HANDLERS:
        del _FETCH_HANDLERS[provider]
        logger.info("已移除 fetch handler: %s", provider)
        return True
    return False


def get_fetch_handlers() -> dict[str, FetchHandler]:
    """Return a shallow copy of the fetch handler registry (for introspection)."""
    return {p: e.handler for p, e in _FETCH_HANDLERS.items()}


def get_fetch_handler_owners() -> dict[str, str | None]:
    """返回 handler → owner 映射（供插件管理器使用）。"""
    return {p: e.owner for p, e in _FETCH_HANDLERS.items()}


def _extract_arxiv_paper_id(url: str) -> str | None:
    """从 arxiv.org 的 abs/html/pdf URL 提取论文 ID。"""
    parsed = urlparse(url)
    if parsed.hostname not in {"arxiv.org", "www.arxiv.org"}:
        return None

    path = parsed.path.rstrip("/")
    for prefix in ("/abs/", "/html/", "/pdf/"):
        if not path.startswith(prefix):
            continue
        paper_id = path[len(prefix) :]
        if prefix == "/pdf/" and paper_id.endswith(".pdf"):
            paper_id = paper_id[:-4]
        return paper_id or None
    return None


def _get_provider_global_timeout(provider: str, url_count: int, timeout: float) -> float:
    """计算 provider 级总超时预算。

    大多数 provider 会在一个请求内完成整批抓取，沿用 ``timeout + 10`` 的宽限。
    ``arxiv_fulltext`` 逐条提取全文，且内部自带 3 秒节流，因此按 URL 数量放大总预算。
    ``xcrawl`` 使用并发度 3 的 semaphore 逐条抓取，按 ceil(url_count/3) 轮放大。
    """
    if provider == "arxiv_fulltext":
        return timeout * max(1, url_count) + 10
    if provider == "xcrawl":
        import math

        waves = math.ceil(max(1, url_count) / 3)
        return timeout * waves + 10
    return timeout + 10


def validate_fetch_url(url: str) -> tuple[bool, str]:
    """SSRF 防护 URL 校验

    仅允许 http/https 协议，解析 DNS 后拒绝私有/内部 IP 地址。

    Args:
        url: 待校验的 URL

    Returns:
        (is_valid, reason) 元组
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL 解析失败"

    if parsed.scheme not in ("http", "https"):
        return False, f"不允许的协议: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "缺少主机名"

    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return False, f"DNS 解析失败: {hostname}"

    for info in infos:
        addr_str = info[4][0]
        # IPv6 scope 后缀（如 fe80::1%eth0）需剥离
        if "%" in addr_str:
            addr_str = addr_str.split("%", 1)[0]
        try:
            addr = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return False, f"目标地址为内部/私有 IP: {addr_str}"

    return True, ""


async def _handle_builtin(
    urls: list[str],
    timeout: float,
    *,
    selector: str | None = None,
    start_index: int = 0,
    max_length: int | None = None,
    respect_robots_txt: bool = False,
    **_kwargs: Any,
) -> FetchResponse:
    from souwen.web.builtin import BuiltinFetcherClient

    async with BuiltinFetcherClient(respect_robots_txt=respect_robots_txt) as client:
        # 涉及 selector / 分页参数时按单 URL 调用以传递参数
        if selector or start_index > 0 or max_length is not None:
            results: list[FetchResult] = []
            for u in urls:
                r = await client.fetch(
                    u,
                    timeout=timeout,
                    start_index=start_index,
                    max_length=max_length,
                    selector=selector,
                )
                results.append(r)
            ok = sum(1 for r in results if r.error is None)
            return FetchResponse(
                urls=urls,
                results=results,
                total=len(results),
                total_ok=ok,
                total_failed=len(results) - ok,
                provider="builtin",
            )
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_jina_reader(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.jina_reader import JinaReaderClient

    config = get_config()
    api_key = getattr(config, "jina_api_key", None) or None
    async with JinaReaderClient(api_key=api_key) as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_arxiv_fulltext(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.paper.arxiv_fulltext import ArxivFulltextClient

    async with ArxivFulltextClient() as client:
        results: list[FetchResult] = []
        for url in urls:
            paper_id = _extract_arxiv_paper_id(url)
            if paper_id is None:
                results.append(
                    FetchResult(
                        url=url,
                        final_url=url,
                        source="arxiv_fulltext",
                        error="arxiv_fulltext 仅支持 arxiv.org 的 /abs/、/html/ 或 /pdf/ URL",
                    )
                )
                continue
            try:
                result = await asyncio.wait_for(
                    client.get_fulltext(paper_id),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                results.append(
                    FetchResult(
                        url=url,
                        final_url=url,
                        source="arxiv_fulltext",
                        error=f"单 URL 超时（{timeout}s）",
                    )
                )
                continue
            except Exception as exc:
                results.append(
                    FetchResult(
                        url=url,
                        final_url=url,
                        source="arxiv_fulltext",
                        error=str(exc),
                    )
                )
                continue
            results.append(result.model_copy(update={"url": url}))

        ok = sum(1 for result in results if result.error is None)
        return FetchResponse(
            urls=urls,
            results=results,
            total=len(results),
            total_ok=ok,
            total_failed=len(results) - ok,
            provider="arxiv_fulltext",
        )


async def _handle_tavily(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.tavily import TavilyClient

    async with TavilyClient() as client:
        return await client.extract(urls, timeout=timeout)


async def _handle_firecrawl(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.firecrawl import FirecrawlClient

    async with FirecrawlClient() as client:
        return await client.scrape_batch(urls, timeout=timeout)


async def _handle_xcrawl(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.xcrawl import XCrawlClient

    async with XCrawlClient() as client:
        return await client.scrape_batch(urls, timeout=timeout)


async def _handle_exa(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.exa import ExaClient

    async with ExaClient() as client:
        return await client.contents(urls, timeout=timeout)


async def _handle_crawl4ai(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.crawl4ai_fetcher import Crawl4AIFetcherClient

    async with Crawl4AIFetcherClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_scrapfly(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.scrapfly import ScrapflyClient

    async with ScrapflyClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_diffbot(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.diffbot import DiffbotClient

    async with DiffbotClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_scrapingbee(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.scrapingbee import ScrapingBeeClient

    async with ScrapingBeeClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_zenrows(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.zenrows import ZenRowsClient

    async with ZenRowsClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_scraperapi(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.scraperapi import ScraperAPIClient

    async with ScraperAPIClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_apify(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.apify import ApifyClient

    async with ApifyClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_cloudflare(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.cloudflare_browser import CloudflareBrowserClient

    async with CloudflareBrowserClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_wayback(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.wayback import WaybackClient

    async with WaybackClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_newspaper(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.newspaper_fetcher import NewspaperFetcherClient

    async with NewspaperFetcherClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_readability(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.readability_fetcher import ReadabilityFetcherClient

    async with ReadabilityFetcherClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_mcp(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.mcp_fetch import MCPFetchClient

    async with MCPFetchClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


async def _handle_site_crawler(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.site_crawler import SiteCrawlerClient

    async with SiteCrawlerClient() as client:
        # max_depth=1 默认爬取根页面 + 一级子页面
        return await client.fetch_batch(urls, timeout=timeout, max_depth=1)


async def _handle_deepwiki(urls: list[str], timeout: float, **_kwargs: Any) -> FetchResponse:
    from souwen.web.deepwiki import DeepWikiClient

    async with DeepWikiClient() as client:
        return await client.fetch_batch(urls, timeout=timeout)


# 注册全部内置 provider 的抓取处理函数（外部插件可通过 register_fetch_handler 扩展）
register_fetch_handler("builtin", _handle_builtin)
register_fetch_handler("jina_reader", _handle_jina_reader)
register_fetch_handler("arxiv_fulltext", _handle_arxiv_fulltext)
register_fetch_handler("tavily", _handle_tavily)
register_fetch_handler("firecrawl", _handle_firecrawl)
register_fetch_handler("xcrawl", _handle_xcrawl)
register_fetch_handler("exa", _handle_exa)
register_fetch_handler("crawl4ai", _handle_crawl4ai)
register_fetch_handler("scrapfly", _handle_scrapfly)
register_fetch_handler("diffbot", _handle_diffbot)
register_fetch_handler("scrapingbee", _handle_scrapingbee)
register_fetch_handler("zenrows", _handle_zenrows)
register_fetch_handler("scraperapi", _handle_scraperapi)
register_fetch_handler("apify", _handle_apify)
register_fetch_handler("cloudflare", _handle_cloudflare)
register_fetch_handler("wayback", _handle_wayback)
register_fetch_handler("newspaper", _handle_newspaper)
register_fetch_handler("readability", _handle_readability)
register_fetch_handler("mcp", _handle_mcp)
register_fetch_handler("site_crawler", _handle_site_crawler)
register_fetch_handler("deepwiki", _handle_deepwiki)


async def _fetch_with_provider(
    provider: str,
    urls: list[str],
    timeout: float,
    **kwargs: Any,
) -> FetchResponse:
    """通过注册表派发到指定 provider 的抓取处理函数。

    Args:
        provider: 提供者名称
        urls: URL 列表
        timeout: 超时秒数
        **kwargs: provider 特定参数（例如 builtin 的 selector / start_index / max_length /
            respect_robots_txt），未识别的参数会被对应 handler 忽略

    Returns:
        FetchResponse
    """
    entry = _FETCH_HANDLERS.get(provider)
    if entry is not None:
        return await entry.handler(urls, timeout, **kwargs)

    # 未知提供者 → 全部标记失败
    results = [
        FetchResult(url=u, final_url=u, source=provider, error=f"未知提供者: {provider}")
        for u in urls
    ]
    return FetchResponse(
        urls=urls,
        results=results,
        total=len(urls),
        total_ok=0,
        total_failed=len(urls),
        provider=provider,
    )


async def fetch_content(
    urls: list[str],
    providers: list[str] | None = None,
    timeout: float = 30.0,
    skip_ssrf_check: bool = False,
    selector: str | None = None,
    start_index: int = 0,
    max_length: int | None = None,
    respect_robots_txt: bool = False,
) -> FetchResponse:
    """并发多提供者聚合内容抓取

    用户显式选择提供者（不自动级联），默认使用 builtin（内置，零配置）。
    每个提供者独立抓取全部 URL 列表中有效的 URL。

    Args:
        urls: 目标 URL 列表
        providers: 提供者列表，默认 ["builtin"]
        timeout: 每个 URL 超时秒数
        skip_ssrf_check: 跳过 SSRF 校验（仅内部使用）

    Returns:
        FetchResponse 聚合结果
    """
    selected = providers or ["builtin"]

    # SSRF 校验
    valid_urls: list[str] = []
    ssrf_failures: list[FetchResult] = []
    if not skip_ssrf_check:
        for url in urls:
            ok, reason = validate_fetch_url(url)
            if ok:
                valid_urls.append(url)
            else:
                ssrf_failures.append(
                    FetchResult(
                        url=url,
                        final_url=url,
                        source="ssrf_check",
                        error=f"SSRF 校验失败: {reason}",
                    )
                )
    else:
        valid_urls = list(urls)

    if not valid_urls:
        return FetchResponse(
            urls=urls,
            results=ssrf_failures,
            total=len(ssrf_failures),
            total_ok=0,
            total_failed=len(ssrf_failures),
            provider=",".join(selected),
            meta={"requested_providers": selected, "ssrf_blocked": len(ssrf_failures)},
        )

    # 用户显式选择单提供者（不做多提供者扇出）
    provider = selected[0]
    global_timeout = _get_provider_global_timeout(provider, len(valid_urls), timeout)

    try:
        resp = await asyncio.wait_for(
            _fetch_with_provider(
                provider,
                valid_urls,
                timeout=timeout,
                selector=selector,
                start_index=start_index,
                max_length=max_length,
                respect_robots_txt=respect_robots_txt,
            ),
            timeout=global_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Fetch 全局超时: provider=%s urls=%d", provider, len(valid_urls))
        resp = FetchResponse(
            urls=valid_urls,
            results=[
                FetchResult(url=u, final_url=u, source=provider, error="全局超时")
                for u in valid_urls
            ],
            total=len(valid_urls),
            total_ok=0,
            total_failed=len(valid_urls),
            provider=provider,
        )
    except Exception as exc:
        logger.warning("Fetch 提供者异常: provider=%s err=%s", provider, exc)
        resp = FetchResponse(
            urls=valid_urls,
            results=[
                FetchResult(url=u, final_url=u, source=provider, error=str(exc)) for u in valid_urls
            ],
            total=len(valid_urls),
            total_ok=0,
            total_failed=len(valid_urls),
            provider=provider,
        )

    # 合并 SSRF 拦截结果
    all_results = ssrf_failures + list(resp.results)
    ok_count = sum(1 for r in all_results if r.error is None)

    return FetchResponse(
        urls=urls,
        results=all_results,
        total=len(all_results),
        total_ok=ok_count,
        total_failed=len(all_results) - ok_count,
        provider=provider,
        meta={"requested_providers": selected, "ssrf_blocked": len(ssrf_failures)},
    )
