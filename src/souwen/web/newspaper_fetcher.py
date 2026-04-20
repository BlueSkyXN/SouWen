"""Newspaper4k 新闻文章抓取客户端

文件用途：
    通过 newspaper4k 开源库抓取新闻文章，输出结构化元数据
    （作者、发布时间、关键词、NLP 摘要、首图等）。专注于新闻类页面，
    与 trafilatura 的通用正文提取互补。newspaper4k 为可选依赖
    （pip install newspaper4k）。

函数/类清单：
    NewspaperFetcherClient（类）
        - 功能：基于 newspaper4k 的新闻文章抓取客户端
        - 关键属性：
            * ENGINE_NAME = "newspaper"
            * PROVIDER_NAME = "newspaper"
        - 主要方法：
            * __aenter__() / __aexit__()  异步上下文管理器
            * fetch(url, timeout) → FetchResult
            * fetch_batch(urls, max_concurrency, timeout) → FetchResponse

模块依赖：
    - newspaper4k: 新闻文章解析库（可选依赖，懒加载）
    - asyncio: 异步并发与 executor 调度
    - logging: 日志记录
    - souwen.exceptions: ConfigError 异常
    - souwen.models: FetchResponse, FetchResult 数据模型

技术要点：
    - newspaper4k 自带 HTTP 抓取，无需继承 SouWenHttpClient
    - newspaper.article() 是同步阻塞函数，需 run_in_executor 调度
    - 懒加载：仅在 __aenter__ 中 import，缺失时抛 ConfigError
    - 输出 plain text（非 markdown），关键字/作者/时间等元数据进入 raw
    - 异常封装到 FetchResult.error，避免中断批量任务
"""

from __future__ import annotations

import asyncio
import logging

from souwen.exceptions import ConfigError
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.newspaper_fetcher")


class NewspaperFetcherClient:
    """Newspaper4k 新闻文章抓取客户端

    专注于新闻文章解析，提供作者、发布时间、关键词、NLP 摘要等结构化元数据。
    需要安装可选依赖：pip install newspaper4k
    """

    ENGINE_NAME = "newspaper"
    PROVIDER_NAME = "newspaper"

    def __init__(self) -> None:
        self._newspaper = None

    async def __aenter__(self):
        try:
            import newspaper
        except ImportError:
            # 抛 ConfigError，install 命令塞到 register_url 字段
            raise ConfigError(
                "newspaper4k",
                "Newspaper",
                "pip install newspaper4k",
            )
        self._newspaper = newspaper
        return self

    async def __aexit__(self, *args):
        # newspaper 无需显式清理资源
        self._newspaper = None

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL 并提取新闻文章结构化数据

        Args:
            url: 目标新闻文章 URL
            timeout: 超时秒数

        Returns:
            FetchResult 包含正文、作者、发布时间等
        """
        if self._newspaper is None:
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error="客户端未初始化，请使用 async with 上下文管理器",
            )
        try:
            # newspaper.article() 是同步函数，丢到默认 executor 执行
            loop = asyncio.get_event_loop()
            article = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._newspaper.article(url)),
                timeout=timeout,
            )

            content = article.text or ""
            title = article.title or ""

            authors = article.authors or []
            author = ", ".join(authors) if authors else None

            published_date = None
            if article.publish_date is not None:
                try:
                    published_date = article.publish_date.isoformat()
                except Exception:
                    published_date = str(article.publish_date)

            snippet = content[:500] if content else ""

            return FetchResult(
                url=url,
                final_url=url,
                title=title,
                content=content,
                content_format="text",
                source=self.PROVIDER_NAME,
                author=author,
                published_date=published_date,
                snippet=snippet,
                raw={
                    "provider": "newspaper",
                    "keywords": article.keywords or [],
                    "top_image": article.top_image or "",
                    "meta_description": article.meta_description or "",
                },
            )
        except asyncio.TimeoutError:
            logger.warning("Newspaper fetch timeout: url=%s timeout=%.1fs", url, timeout)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=f"抓取超时 ({timeout}s)",
            )
        except Exception as exc:
            logger.warning("Newspaper fetch failed: url=%s err=%s", url, exc)
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
            max_concurrency: 最大并发数（受 executor 线程池限制，默认 3）
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
