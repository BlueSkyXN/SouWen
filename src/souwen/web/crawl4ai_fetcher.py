"""Crawl4AI 内容抓取客户端

文件用途：
    通过 Crawl4AI 开源库（基于 Playwright 无头浏览器）抓取网页内容。
    适合 JS 渲染重度页面，输出干净 Markdown。免费、零 API Key、本地运行。
    Crawl4AI 为可选依赖（pip install souwen[crawl4ai]）。

函数/类清单：
    Crawl4AIFetcherClient（类）
        - 功能：Crawl4AI 内容抓取客户端
        - 关键属性：PROVIDER_NAME = "crawl4ai"
        - 主要方法：
            * fetch(url, timeout) → FetchResult
            * fetch_batch(urls, max_concurrency, timeout) → FetchResponse

模块依赖：
    - crawl4ai: 开源 AI 爬虫库（可选依赖）
    - asyncio: 并发控制
    - logging: 日志记录

技术要点：
    - Crawl4AI 基于 Playwright，需要浏览器二进制（约 300MB）
    - 使用 AsyncWebCrawler 异步模式
    - 懒加载：仅在实际调用时 import crawl4ai，避免启动时加载
    - 作为可选依赖 [crawl4ai] extra 发布
"""

from __future__ import annotations

import asyncio
import logging

from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.crawl4ai_fetcher")


class Crawl4AIFetcherClient:
    """Crawl4AI 无头浏览器内容抓取客户端

    基于 Playwright，适合 JS 渲染重度页面。零 API Key，本地运行。
    需要安装可选依赖：pip install souwen[crawl4ai]
    """

    PROVIDER_NAME = "crawl4ai"

    def __init__(self) -> None:
        self._crawler = None

    async def __aenter__(self):
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError:
            from souwen.exceptions import ConfigError

            raise ConfigError(
                "crawl4ai",
                "Crawl4AI",
                "pip install souwen[crawl4ai]",
            )
        self._crawler = AsyncWebCrawler(verbose=False)
        await self._crawler.__aenter__()
        return self

    async def __aexit__(self, *args):
        if self._crawler is not None:
            await self._crawler.__aexit__(*args)
            self._crawler = None

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL 的内容

        Args:
            url: 目标网页 URL
            timeout: 超时秒数

        Returns:
            FetchResult 包含提取的 Markdown 内容
        """
        if self._crawler is None:
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error="客户端未初始化，请使用 async with 上下文管理器",
            )
        try:
            result = await asyncio.wait_for(
                self._crawler.arun(url=url),
                timeout=timeout,
            )

            content = getattr(result, "markdown", "") or ""
            if not content:
                md_v2 = getattr(result, "markdown_v2", None)
                if md_v2:
                    content = getattr(md_v2, "raw_markdown", "") or str(md_v2)

            metadata = getattr(result, "metadata", {}) or {}
            title = ""
            if isinstance(metadata, dict):
                title = metadata.get("title", "") or ""

            final_url = getattr(result, "url", url) or url

            snippet = content[:500] if content else ""

            success = getattr(result, "success", bool(content))
            if not success and not content:
                error_msg = (
                    getattr(result, "error_message", None) or "抓取失败（页面可能无内容或渲染超时）"
                )
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    source=self.PROVIDER_NAME,
                    error=error_msg,
                )

            return FetchResult(
                url=url,
                final_url=final_url,
                title=title,
                content=content,
                content_format="markdown",
                source=self.PROVIDER_NAME,
                snippet=snippet,
                raw={"provider": "crawl4ai"},
            )
        except asyncio.TimeoutError:
            logger.warning("Crawl4AI fetch timeout: url=%s timeout=%.1fs", url, timeout)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=f"抓取超时 ({timeout}s)",
            )
        except Exception as exc:
            logger.warning("Crawl4AI fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 3,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数（受浏览器内存限制，默认 3）
            timeout: 每个 URL 超时

        Returns:
            FetchResponse 聚合结果
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.fetch(u, timeout=timeout)

        results = await asyncio.gather(*[_fetch_one(u) for u in urls])
        result_list = list(results)
        ok = sum(1 for r in result_list if r.error is None)
        return FetchResponse(
            urls=urls,
            results=result_list,
            total=len(result_list),
            total_ok=ok,
            total_failed=len(result_list) - ok,
            provider=self.PROVIDER_NAME,
        )
