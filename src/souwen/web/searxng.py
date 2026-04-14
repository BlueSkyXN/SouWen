"""SearXNG 元搜索 API 客户端

通过 SearXNG 自建实例的 JSON API 聚合 250+ 搜索引擎结果。
用户需自行部署 SearXNG 实例。

接口: GET /search?q=QUERY&format=json&engines=ENGINE1,ENGINE2
文档: https://docs.searxng.org/dev/search_api.html

特点：
- 一个接入即获 250+ 引擎（Google, Bing, DuckDuckGo 等）
- 支持按 category 筛选（general, images, videos, news, science）
- 支持指定引擎子集
- 需自部署实例（公共实例不稳定）
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.searxng")


class SearXNGClient(SouWenHttpClient):
    """SearXNG JSON API 客户端

    Args:
        instance_url: SearXNG 实例 URL (如 http://localhost:8888)
                     默认从 SOUWEN_SEARXNG_URL 环境变量读取
    """

    ENGINE_NAME = "searxng"

    def __init__(self, instance_url: str | None = None):
        config = get_config()
        self.instance_url = (instance_url or config.resolve_api_key("searxng", "searxng_url") or "").rstrip("/")
        if not self.instance_url:
            raise ConfigError(
                "searxng_url",
                "SearXNG",
                "https://docs.searxng.org/admin/installation.html",
            )
        super().__init__(base_url=self.instance_url, source_name="searxng")

    async def search(
        self,
        query: str,
        max_results: int = 20,
        engines: str | None = None,
        categories: str | None = None,
        language: str = "auto",
    ) -> WebSearchResponse:
        """通过 SearXNG JSON API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            engines: 指定引擎（逗号分隔，如 "google,bing,duckduckgo"）
            categories: 分类筛选（如 "general", "science", "news"）
            language: 语言（如 "zh-CN", "en-US", "auto"）
        """
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "language": language,
        }
        if engines:
            params["engines"] = engines
        if categories:
            params["categories"] = categories

        resp = await self.get("/search", params=params)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"SearXNG 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("results", []):
            if len(results) >= max_results:
                break
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                continue
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_SEARXNG,
                    title=title,
                    url=url,
                    snippet=item.get("content", "").strip(),
                    engine=item.get("engine", self.ENGINE_NAME),
                )
            )

        logger.info("SearXNG 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_SEARXNG,
            results=results,
            total_results=data.get("number_of_results", 0) or len(results),
        )
