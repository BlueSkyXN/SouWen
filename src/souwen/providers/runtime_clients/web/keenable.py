"""Keenable 搜索 API 客户端

文件用途：
    Keenable 网页搜索 API 客户端，通过官方 REST API（POST /v1/search，
    X-API-Key 认证）返回结构化搜索结果。

函数/类清单：
    KeenableClient（类）
        - 功能：Keenable 搜索客户端
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "keenable", BASE_URL = "https://api.keenable.ai"
        - 主要方法：search(query, max_results) -> WebSearchResponse

技术要点：
    - API 端点：/v1/search，请求体 {"query", "max_results"}
    - X-API-Key 头认证，X-Keenable-Title 标识调用方
    - 摘要优先使用 description，降级到截断后的 snippet
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.common_runtime.provider_support.exceptions import ConfigError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.providers.runtime_clients.models import WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.providers.runtime_clients.web.keenable")

_SNIPPET_MAX_CHARS = 500


class KeenableClient(SouWenHttpClient):
    """Keenable 搜索客户端

    Args:
        api_key: Keenable API Key，默认从 SOUWEN_KEENABLE_API_KEY 读取
    """

    ENGINE_NAME = "keenable"
    BASE_URL = "https://api.keenable.ai"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("keenable", "keenable_api_key")
        if not self.api_key:
            raise ConfigError(
                "keenable_api_key",
                "Keenable",
                "https://keenable.ai/",
            )
        super().__init__(
            base_url=self.BASE_URL,
            source_name="keenable",
            headers={"X-API-Key": self.api_key, "X-Keenable-Title": "SouWen"},
        )

    async def search(self, query: str, max_results: int = 10) -> WebSearchResponse:
        """通过 Keenable API 搜索"""
        payload: dict[str, Any] = {"query": query, "max_results": max_results}
        resp = await self.post("/v1/search", json=payload)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.common_runtime.provider_support.exceptions import ParseError

            raise ParseError(f"Keenable 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("results") or []:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url:
                continue
            snippet = (item.get("description") or "").strip() or (
                item.get("snippet") or ""
            ).strip()[:_SNIPPET_MAX_CHARS]
            results.append(
                WebSearchResult(
                    source="keenable",
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw={},
                )
            )
            if len(results) >= max_results:
                break

        logger.info("Keenable 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="keenable",
            results=results,
            total_results=len(results),
        )
