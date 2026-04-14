"""Linkup 搜索 API 客户端

Linkup 提供结构化的网页搜索 API，支持不同搜索深度。
适合需要快速获取搜索结果的场景。

接口: POST https://api.linkup.so/v1/search
文档: https://docs.linkup.so/

特点：
- 支持标准和深度搜索模式
- 结构化 JSON 结果
- 支持多种输出类型（搜索结果、内容提取等）
- 简洁的 API 设计
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.linkup")


class LinkupClient(SouWenHttpClient):
    """Linkup 搜索客户端

    Args:
        api_key: Linkup API Key，默认从 SOUWEN_LINKUP_API_KEY 读取
    """

    ENGINE_NAME = "linkup"
    BASE_URL = "https://api.linkup.so"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("linkup", "linkup_api_key")
        if not self.api_key:
            raise ConfigError(
                "linkup_api_key",
                "Linkup",
                "https://www.linkup.so/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="linkup")
        self.headers["Authorization"] = f"Bearer {self.api_key}"

    async def search(
        self,
        query: str,
        max_results: int = 10,
        depth: str = "standard",
        output_type: str = "searchResults",
    ) -> WebSearchResponse:
        """通过 Linkup API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            depth: 搜索深度 "standard" 或 "deep"
            output_type: 输出类型 "searchResults" / "sourcedAnswer" 等
        """
        payload: dict[str, Any] = {
            "q": query,
            "depth": depth,
            "outputType": output_type,
            "maxResults": max_results,
        }

        resp = await self.post("/v1/search", json=payload)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Linkup 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("results", []):
            title = (item.get("name") or item.get("title", "")).strip()
            url = item.get("url", "").strip()
            if not title or not url:
                continue
            snippet = (item.get("content") or item.get("snippet", "")).strip()
            raw: dict[str, Any] = {}
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_LINKUP,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Linkup 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_LINKUP,
            results=results,
            total_results=len(results),
        )
