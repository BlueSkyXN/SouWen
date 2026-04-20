"""Newspaper4k 新闻文章抓取客户端

文件用途：
    基于 SouWen 现有 HTTP 基础设施（httpx / curl_cffi）和 newspaper4k 的
    新闻文章抓取客户端。继承 BaseScraper 获得 TLS 指纹伪装、WARP 代理、
    自适应退避等反反爬能力，仅使用 newspaper4k 做 HTML 解析（作者、发布
    时间、关键词、首图、meta 描述等结构化元数据），HTTP 抓取走自有栈。

    专注于新闻类页面，与 trafilatura 的通用正文提取互补。newspaper4k 为
    可选依赖（pip install newspaper4k）。

函数/类清单：
    NewspaperFetcherClient（类）
        - 功能：基于 newspaper4k 的新闻文章抓取客户端
        - 继承：BaseScraper（爬虫基类，提供 TLS 指纹 / WARP / 退避）
        - 关键属性：
            * ENGINE_NAME = "newspaper"
            * PROVIDER_NAME = "newspaper"
        - 主要方法：
            * __aenter__() / __aexit__()  异步上下文管理器
            * fetch(url, timeout) → FetchResult
            * fetch_batch(urls, max_concurrency, timeout) → FetchResponse

模块依赖：
    - newspaper4k: 新闻文章解析库（可选依赖，懒加载）
    - asyncio: 异步并发与 to_thread 调度
    - logging: 日志记录
    - souwen.exceptions: ConfigError 异常
    - souwen.scraper.base: BaseScraper 基类
    - souwen.models: FetchResponse, FetchResult 数据模型

技术要点：
    - HTTP 抓取走 BaseScraper._fetch（curl_cffi TLS 指纹 + WARP + 自适应退避）
    - newspaper4k 仅做解析：调用 newspaper.article(url, input_html=html) 跳过其
      自带的 requests 下载，避免绕过 SouWen HTTP 栈
    - newspaper.article() 是同步阻塞函数，需 asyncio.to_thread 移出事件循环
    - 懒加载：仅在 __aenter__ 中 import newspaper，缺失时抛 ConfigError
    - 输出 plain text（非 markdown），关键字/作者/时间等元数据进入 raw
    - 异常封装到 FetchResult.error，避免中断批量任务
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from souwen.exceptions import ConfigError
from souwen.models import FetchResponse, FetchResult
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.newspaper_fetcher")


class NewspaperFetcherClient(BaseScraper):
    """Newspaper4k 新闻文章抓取客户端

    使用 SouWen 自有的 HTTP 栈（httpx / curl_cffi + TLS 指纹 + WARP）抓取网页，
    用 newspaper4k 解析新闻文章，提供作者、发布时间、关键词、首图等结构化元数据。

    需要安装可选依赖：pip install newspaper4k
    """

    ENGINE_NAME = "newspaper"
    PROVIDER_NAME = "newspaper"

    def __init__(self) -> None:
        # newspaper 解析在本地完成，HTTP 部分由 BaseScraper 自身的退避控制；
        # 此处不做额外礼貌延迟，保持与 readability/builtin 一致的低延迟策略。
        super().__init__(
            min_delay=0.0,
            max_delay=0.0,
            max_retries=2,
            follow_redirects=True,
        )
        self._newspaper: Any = None

    async def __aenter__(self) -> "NewspaperFetcherClient":
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
        await super().__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        try:
            await super().__aexit__(*args)
        finally:
            self._newspaper = None

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL 并提取新闻文章结构化数据

        HTTP 抓取由 BaseScraper._fetch 完成（含 TLS 指纹、WARP、退避），
        随后将 HTML 交给 newspaper4k 仅做解析（input_html 参数跳过其自带下载）。

        Args:
            url: 目标新闻文章 URL
            timeout: 超时秒数（覆盖整个抓取 + 解析流程）

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
            # 1) BaseScraper 抓 HTML（curl_cffi/httpx + WARP + 退避）
            resp = await asyncio.wait_for(self._fetch(url), timeout=timeout)
            final_url = url
            html = resp.text or ""
            status_code = resp.status_code

            if not html:
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    source=self.PROVIDER_NAME,
                    error="页面内容为空",
                    raw={"provider": "newspaper", "status_code": status_code},
                )

            # 2) newspaper4k 仅解析（input_html 跳过其自带 requests 下载）
            newspaper = self._newspaper
            article = await asyncio.wait_for(
                asyncio.to_thread(newspaper.article, url, input_html=html),
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
                final_url=final_url,
                title=title,
                content=content,
                content_format="text",
                source=self.PROVIDER_NAME,
                author=author,
                published_date=published_date,
                snippet=snippet,
                raw={
                    "provider": "newspaper",
                    "status_code": status_code,
                    "content_length": len(html),
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
