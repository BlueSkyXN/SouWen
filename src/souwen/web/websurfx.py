"""Client for WebSurfX

Purpose:
    Privacy-focused meta-search engine

API Endpoint:
    WebSurfX service

Key Features:
    - Aggregates results, no user tracking, self-hosted support

Engine Class:
    WebsurfxClient(SouWenHttpClient)
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

logger = logging.getLogger("souwen.web.websurfx")


class WebsurfxClient(SouWenHttpClient):
    """Websurfx JSON API 客户端

    Args:
        instance_url: Websurfx 实例 URL (如 http://localhost:8080)
                     默认从 SOUWEN_WEBSURFX_URL 环境变量读取
    """

    ENGINE_NAME = "websurfx"

    def __init__(self, instance_url: str | None = None):
        config = get_config()
        self.instance_url = (
            instance_url or config.resolve_api_key("websurfx", "websurfx_url") or ""
        ).rstrip("/")
        if not self.instance_url:
            raise ConfigError(
                "websurfx_url",
                "Websurfx",
                "https://github.com/neon-mmd/websurfx",
            )
        super().__init__(base_url=self.instance_url, source_name="websurfx")

    async def search(
        self,
        query: str,
        max_results: int = 20,
    ) -> WebSearchResponse:
        """通过 Websurfx JSON API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
        }

        resp = await self.get("/search", params=params)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Websurfx 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("results", []):
            if len(results) >= max_results:
                break
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                continue
            snippet = (item.get("description") or item.get("content") or "").strip()
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_WEBSURFX,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                )
            )

        logger.info("Websurfx 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_WEBSURFX,
            results=results,
            total_results=len(results),
        )
