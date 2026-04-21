"""facade/fetch.py — 内容抓取门面

把 fetch 请求派发给 registry 中声明了 `fetch` capability 的 adapter。

公开 API：
  - fetch_content(urls, provider='builtin', timeout=30.0, **kw) → FetchResponse

行为与 v0 `souwen.web.fetch.fetch_content` 保持一致；v0 入口继续可用。
"""

from __future__ import annotations

import logging

from souwen.registry import get as _registry_get

logger = logging.getLogger("souwen.facade.fetch")


async def fetch_content(
    urls: list[str],
    provider: str = "builtin",
    timeout: float = 30.0,
    **kwargs,
):
    """通过 registry 里声明 fetch 能力的 adapter 抓取内容。

    v0 的 `souwen.web.fetch.fetch_content` 已经实现了 SSRF 防护、重定向跟踪、
    响应聚合等完整管道逻辑。本门面**委托**给它，而不是重写。

    Args:
        urls: 要抓取的 URL 列表
        provider: 抓取提供者名字（builtin / jina_reader / crawl4ai / tavily / firecrawl / ...）
            必须是 registry 中声明了 `fetch` capability 的源
        timeout: 单个 URL 抓取超时（秒）
        **kwargs: 透传给 provider

    Returns:
        FetchResponse（v0 格式）

    Raises:
        ValueError: provider 在 registry 中未声明 fetch capability
    """
    adapter = _registry_get(provider)
    if adapter is None:
        raise ValueError(f"unknown fetch provider: {provider!r}")
    if "fetch" not in adapter.capabilities:
        raise ValueError(
            f"provider {provider!r} 不支持 fetch capability "
            f"(has: {sorted(adapter.capabilities)})"
        )

    # 委托给 v0 的实现（该实现已经内置了 SSRF 防护 / 重定向 / 批量聚合等管道逻辑）
    from souwen.web.fetch import fetch_content as _v0_fetch

    return await _v0_fetch(urls, provider=provider, timeout=timeout, **kwargs)
