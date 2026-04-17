"""Client for SerpAPI

Purpose:
    Google SERP and news search results

API Endpoint:
    SerpAPI service

Key Features:
    - Structured JSON for Google search results with news data

Engine Class:
    SerpapiClient(SouWenHttpClient)
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

logger = logging.getLogger("souwen.web.serpapi")


class SerpApiClient(SouWenHttpClient):
    """SerpAPI 搜索客户端

    Args:
        api_key: SerpAPI API Key，默认从 SOUWEN_SERPAPI_API_KEY 读取
    """

    ENGINE_NAME = "serpapi"
    BASE_URL = "https://serpapi.com"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("serpapi", "serpapi_api_key")
        if not self.api_key:
            raise ConfigError(
                "serpapi_api_key",
                "SerpAPI",
                "https://serpapi.com/manage-api-key",
            )
        super().__init__(base_url=self.BASE_URL, source_name="serpapi")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        engine: str = "google",
    ) -> WebSearchResponse:
        """通过 SerpAPI 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            engine: 搜索引擎 "google" / "bing" / "yahoo" / "baidu" 等
        """
        params: dict[str, Any] = {
            "engine": engine,
            "q": query,
            "api_key": self.api_key,
            "num": max_results,
        }

        resp = await self.get("/search", params=params)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"SerpAPI 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("organic_results", []):
            title = item.get("title", "").strip()
            url = item.get("link", "").strip()
            if not title or not url:
                continue
            raw: dict[str, Any] = {}
            if item.get("position"):
                raw["position"] = item["position"]
            if item.get("date"):
                raw["date"] = item["date"]
            if item.get("source"):
                raw["source"] = item["source"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_SERPAPI,
                    title=title,
                    url=url,
                    snippet=item.get("snippet", "").strip(),
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        # Knowledge Graph 和 Related Questions
        kg = data.get("knowledge_graph")
        related = data.get("related_questions")
        raw_resp: dict[str, Any] = {}
        if kg:
            raw_resp["knowledge_graph"] = kg
        if related:
            raw_resp["related_questions"] = related

        logger.info("SerpAPI 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_SERPAPI,
            results=results,
            total_results=len(results),
        )
