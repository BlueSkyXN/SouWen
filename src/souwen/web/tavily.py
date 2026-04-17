"""Client for Tavily

Purpose:
    AI-powered research search API

API Endpoint:
    Tavily service

Key Features:
    - Web search with automatic query expansion and deduplication

Engine Class:
    TavilyClient(SouWenHttpClient)
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

logger = logging.getLogger("souwen.web.tavily")


class TavilyClient(SouWenHttpClient):
    """Tavily AI 搜索客户端

    Args:
        api_key: Tavily API Key，默认从 SOUWEN_TAVILY_API_KEY 读取
    """

    ENGINE_NAME = "tavily"
    BASE_URL = "https://api.tavily.com"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("tavily", "tavily_api_key")
        if not self.api_key:
            raise ConfigError(
                "tavily_api_key",
                "Tavily",
                "https://app.tavily.com/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="tavily")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        include_answer: bool = False,
        include_raw_content: bool = False,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> WebSearchResponse:
        """通过 Tavily API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数 (最大20)
            search_depth: 搜索深度 "basic" 或 "advanced"
            include_answer: 是否返回 AI 生成的答案摘要
            include_raw_content: 是否返回页面原始内容
            include_domains: 限定域名列表
            exclude_domains: 排除域名列表
        """
        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": min(max_results, 20),
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        resp = await self.post("/search", json=payload)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Tavily 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("results", []):
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                continue
            # Tavily 的 content 字段是提取后的页面内容（比 snippet 更丰富）
            snippet = item.get("content", "").strip()
            raw: dict[str, Any] = {}
            if item.get("score"):
                raw["relevance_score"] = item["score"]
            if item.get("raw_content"):
                raw["raw_content"] = item["raw_content"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_TAVILY,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        # Tavily 的 AI 答案摘要
        answer = data.get("answer")
        raw_resp: dict[str, Any] = {}
        if answer:
            raw_resp["ai_answer"] = answer

        logger.info("Tavily 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_TAVILY,
            results=results,
            total_results=len(results),
        )
