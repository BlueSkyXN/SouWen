"""并发多提供者聚合内容抓取

文件用途：
    核心网页内容抓取聚合模块。支持 4 个提供者（Jina Reader、Tavily、Firecrawl、Exa），
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
        - 关键变量：分支 jina_reader / tavily / firecrawl / exa

    fetch_content(urls, providers=None, timeout=30.0, skip_ssrf_check=False) -> FetchResponse
        - 功能：并发多提供者聚合抓取入口（用户显式选择提供者，不自动级联）
        - 输入：urls 目标 URL 列表, providers 提供者列表(默认 ["jina_reader"]),
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
    - souwen.web.jina_reader / tavily / firecrawl / exa: 各提供者客户端（懒加载）

技术要点：
    - SSRF 防护：解析 DNS 后逐个 IP 校验，拒绝私有/回环/链路本地/保留段
    - 提供者懒加载：在分支内 import，避免循环依赖与不必要的依赖加载
    - 用户显式选择提供者：默认 jina_reader（免费），不自动级联付费提供者
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
) -> FetchResponse:
    """使用指定提供者抓取内容

    Args:
        provider: 提供者名称
        urls: URL 列表
        timeout: 超时秒数

    Returns:
        FetchResponse
    """
    if provider == "jina_reader":
        from souwen.web.jina_reader import JinaReaderClient

        config = get_config()
        api_key = getattr(config, "jina_api_key", None) or None
        async with JinaReaderClient(api_key=api_key) as client:
            return await client.fetch_batch(urls, timeout=timeout)

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
) -> FetchResponse:
    """并发多提供者聚合内容抓取

    用户显式选择提供者（不自动级联），默认使用 jina_reader（免费）。
    每个提供者独立抓取全部 URL 列表中有效的 URL。

    Args:
        urls: 目标 URL 列表
        providers: 提供者列表，默认 ["jina_reader"]
        timeout: 每个 URL 超时秒数
        skip_ssrf_check: 跳过 SSRF 校验（仅内部使用）

    Returns:
        FetchResponse 聚合结果
    """
    selected = providers or ["jina_reader"]

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

    try:
        resp = await asyncio.wait_for(
            _fetch_with_provider(provider, valid_urls, timeout=timeout),
            timeout=timeout + 10,  # 超出每 URL 超时的全局宽限期
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
