"""Client for ScrapingDog

Purpose:
    Web scraping with rotating proxies

API Endpoint:
    ScrapingDog service

Key Features:
    - JavaScript rendering, proxy rotation, session handling

Engine Class:
    ScrapingdogClient(SouWenHttpClient)
        async def search(query, max_results) -> WebSearchResponse

Returns:
    WebSearchResponse with title, url, snippet fields
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.scrapingdog")


class ScrapingDogClient(SouWenHttpClient):
    """ScrapingDog Google 搜索客户端

    Args:
        api_key: ScrapingDog API Key，默认从 SOUWEN_SCRAPINGDOG_API_KEY 读取
    """

    ENGINE_NAME = "scrapingdog"
    BASE_URL = "https://api.scrapingdog.com"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("scrapingdog", "scrapingdog_api_key")
        if not self.api_key:
            raise ConfigError(
                "scrapingdog_api_key",
                "ScrapingDog",
                "https://www.scrapingdog.com/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="scrapingdog")

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> WebSearchResponse:
        """通过 ScrapingDog API 搜索 Google

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "results": max_results,
        }

        resp = await self.get("/google", params=params)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"ScrapingDog 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("organic_data", []):
            title = item.get("title", "").strip()
            url = item.get("link", "").strip()
            if not title or not url:
                continue
            raw: dict[str, Any] = {}
            if item.get("position"):
                raw["position"] = item["position"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_SCRAPINGDOG,
                    title=title,
                    url=url,
                    snippet=item.get("snippet", "").strip(),
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("ScrapingDog 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_SCRAPINGDOG,
            results=results,
            total_results=len(results),
        )
