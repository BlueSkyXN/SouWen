"""并发多提供者聚合内容抓取

文件用途：
    核心网页内容抓取聚合模块。支持 20 个提供者（内置抓取、Jina Reader、arXiv Fulltext、
    Tavily、Firecrawl、Exa、Crawl4AI、Scrapfly、Diffbot、ScrapingBee、ZenRows、
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
import ipaddress
import logging
import socket
from urllib.parse import urlparse

from souwen.config import get_config
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.fetch")


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
    ``arxiv_fulltext`` 逐条提取全文，且内部自带 3 秒节流，因此按 URL 数量放大总预算，
    避免健康请求在批量时被聚合层全局超时一锅端。
    """
    if provider == "arxiv_fulltext":
        return timeout * max(1, url_count) + 10
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


async def _fetch_with_provider(
    provider: str,
    urls: list[str],
    timeout: float,
    selector: str | None = None,
    start_index: int = 0,
    max_length: int | None = None,
    respect_robots_txt: bool = False,
) -> FetchResponse:
    """使用指定提供者抓取内容

    Args:
        provider: 提供者名称
        urls: URL 列表
        timeout: 超时秒数
        selector: CSS 选择器（仅 builtin 支持）
        start_index: 内容起始切片位置（仅 builtin 支持）
        max_length: 内容最大长度（仅 builtin 支持）
        respect_robots_txt: 是否遵守 robots.txt（仅 builtin 支持）

    Returns:
        FetchResponse
    """
    if provider == "builtin":
        from souwen.web.builtin import BuiltinFetcherClient

        async with BuiltinFetcherClient(respect_robots_txt=respect_robots_txt) as client:
            # 涉及 selector / 分页参数时按单 URL 调用以传递参数
            if selector or start_index > 0 or max_length is not None:
                results = []
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

    elif provider == "jina_reader":
        from souwen.web.jina_reader import JinaReaderClient

        config = get_config()
        api_key = getattr(config, "jina_api_key", None) or None
        async with JinaReaderClient(api_key=api_key) as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "arxiv_fulltext":
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

    elif provider == "tavily":
        from souwen.web.tavily import TavilyClient

        async with TavilyClient() as client:
            return await client.extract(urls, timeout=timeout)

    elif provider == "firecrawl":
        from souwen.web.firecrawl import FirecrawlClient

        async with FirecrawlClient() as client:
            return await client.scrape_batch(urls, timeout=timeout)

    elif provider == "exa":
        from souwen.web.exa import ExaClient

        async with ExaClient() as client:
            return await client.contents(urls, timeout=timeout)

    elif provider == "crawl4ai":
        from souwen.web.crawl4ai_fetcher import Crawl4AIFetcherClient

        async with Crawl4AIFetcherClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "scrapfly":
        from souwen.web.scrapfly import ScrapflyClient

        async with ScrapflyClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "diffbot":
        from souwen.web.diffbot import DiffbotClient

        async with DiffbotClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "scrapingbee":
        from souwen.web.scrapingbee import ScrapingBeeClient

        async with ScrapingBeeClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "zenrows":
        from souwen.web.zenrows import ZenRowsClient

        async with ZenRowsClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "scraperapi":
        from souwen.web.scraperapi import ScraperAPIClient

        async with ScraperAPIClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "apify":
        from souwen.web.apify import ApifyClient

        async with ApifyClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "cloudflare":
        from souwen.web.cloudflare_browser import CloudflareBrowserClient

        async with CloudflareBrowserClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "wayback":
        from souwen.web.wayback import WaybackClient

        async with WaybackClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "newspaper":
        from souwen.web.newspaper_fetcher import NewspaperFetcherClient

        async with NewspaperFetcherClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "readability":
        from souwen.web.readability_fetcher import ReadabilityFetcherClient

        async with ReadabilityFetcherClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "mcp":
        from souwen.web.mcp_fetch import MCPFetchClient

        async with MCPFetchClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    elif provider == "site_crawler":
        from souwen.web.site_crawler import SiteCrawlerClient

        async with SiteCrawlerClient() as client:
            # max_depth=1 默认爬取根页面 + 一级子页面
            return await client.fetch_batch(urls, timeout=timeout, max_depth=1)

    elif provider == "deepwiki":
        from souwen.web.deepwiki import DeepWikiClient

        async with DeepWikiClient() as client:
            return await client.fetch_batch(urls, timeout=timeout)

    else:
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
