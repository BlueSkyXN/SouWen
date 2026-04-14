"""Firecrawl 搜索 API 客户端

Firecrawl 提供网页抓取与搜索 API，支持返回 Markdown 格式的页面内容。
适合需要获取页面正文内容的搜索场景。

接口: POST https://api.firecrawl.dev/v1/search
文档: https://docs.firecrawl.dev/

特点：
- 搜索 + 内容提取一体化
- 支持返回 Markdown 格式
- 自动提取主要内容（过滤导航、广告等）
- 支持多种输出格式
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.firecrawl")


class FirecrawlClient(SouWenHttpClient):
    """Firecrawl 搜索客户端

    Args:
        api_key: Firecrawl API Key，默认从 SOUWEN_FIRECRAWL_API_KEY 读取
    """

    ENGINE_NAME = "firecrawl"
    BASE_URL = "https://api.firecrawl.dev"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("firecrawl", "firecrawl_api_key")
        if not self.api_key:
            raise ConfigError(
                "firecrawl_api_key",
                "Firecrawl",
                "https://www.firecrawl.dev/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="firecrawl")
        self.headers["Authorization"] = f"Bearer {self.api_key}"

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> WebSearchResponse:
        """通过 Firecrawl API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        payload: dict[str, Any] = {
            "query": query,
            "limit": max_results,
            "scrapeOptions": {
                "formats": ["markdown"],
                "onlyMainContent": True,
            },
        }

        resp = await self.post("/v1/search", json=payload)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Firecrawl 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("data", []):
            metadata = item.get("metadata", {})
            title = (metadata.get("title") or item.get("title", "")).strip()
            url = (item.get("url", "")).strip()
            if not title or not url:
                continue
            snippet = (metadata.get("description") or item.get("description", "")).strip()
            raw: dict[str, Any] = {}
            if item.get("markdown"):
                raw["markdown"] = item["markdown"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_FIRECRAWL,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Firecrawl 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_FIRECRAWL,
            results=results,
            total_results=len(results),
        )
