"""Websurfx 元搜索 API 客户端

通过自建 Websurfx 实例的 JSON API 聚合多个搜索引擎结果。
用户需自行部署 Websurfx 实例。

接口: GET /search?q=QUERY&format=json
项目: https://github.com/neon-mmd/websurfx

特点：
- 类似 SearXNG 的开源元搜索引擎
- 支持 JSON API 直接返回结构化结果
- 高性能异步架构 (Rust 实现)
- 需自部署实例
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
        self.instance_url = (instance_url or config.resolve_api_key("websurfx", "websurfx_url") or "").rstrip("/")
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
