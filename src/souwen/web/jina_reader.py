"""Jina Reader 内容抓取客户端

文件用途：
    通过 Jina Reader API (https://r.jina.ai/<url>) 抓取网页内容并转换为
    Markdown 格式。免费使用（~20 RPM），可通过 JINA_API_KEY 提升额度（~200 RPM）。

函数/类清单：
    JinaReaderClient（类）
        - 功能：Jina Reader 内容抓取客户端
        - 继承：SouWenHttpClient
        - 关键属性：
            ENGINE_NAME = "jina_reader"
            BASE_URL    = "https://r.jina.ai"
        - 主要方法：
            * fetch(url) → FetchResult
            * fetch_batch(urls, max_concurrency) → FetchResponse

模块依赖：
    - asyncio: 并发控制
    - logging: 日志记录
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class JinaReaderClient(SouWenHttpClient):
    """Jina Reader 内容抓取客户端

    通过 r.jina.ai 代理服务将网页转换为干净的 Markdown 文本。
    免费可用，设置 API Key 可提升限额。
    """

    ENGINE_NAME = "jina_reader"
    BASE_URL = "https://r.jina.ai"
    PROVIDER_NAME = "jina_reader"

    def __init__(self, api_key: str | None = None) -> None:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "X-Return-Format": "markdown",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        super().__init__(
            base_url=self.BASE_URL,
            source_name="jina_reader",
            headers=headers,
        )
        self._api_key = api_key

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL 的内容

        Args:
            url: 目标网页 URL
            timeout: 超时秒数

        Returns:
            FetchResult 包含提取的 Markdown 内容
        """
        try:
            resp = await self.get(f"/{url}")
            # Jina Reader JSON 响应格式:
            # { "code": 200, "status": ..., "data": { "title": ..., "content": ..., "url": ... } }
            data = resp.json()
            if isinstance(data, dict):
                inner = data.get("data", data)
                content = inner.get("content", "")
                title = inner.get("title", "")
                final_url = inner.get("url", url)
                snippet = content[:500] if content else ""
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    title=title,
                    content=content,
                    content_format="markdown",
                    source=self.PROVIDER_NAME,
                    snippet=snippet,
                    published_date=inner.get("publishedTime"),
                    author=inner.get("author"),
                    raw={"provider": "jina_reader", "has_key": bool(self._api_key)},
                )
            # 纯文本响应回退
            text = resp.text
            return FetchResult(
                url=url,
                final_url=url,
                content=text,
                content_format="markdown",
                source=self.PROVIDER_NAME,
                snippet=text[:500],
                raw={"provider": "jina_reader", "format": "plain"},
            )
        except Exception as exc:
            logger.warning("Jina Reader fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 5,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数（Jina 免费 ~20 RPM）
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
