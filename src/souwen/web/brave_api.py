"""Brave Search 官方 API 客户端

Brave 搜索的官方 REST API（区别于爬虫方式）。
拥有独立索引，隐私优先。

接口: GET https://api.search.brave.com/res/v1/web/search
文档: https://brave.com/search/api/

特点：
- 官方 API，比爬虫稳定
- 独立索引（非 Google/Bing 驱动）
- 免费档 2000 次/月
- 支持 Web / News / Video 搜索
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.brave_api")


class BraveApiClient(SouWenHttpClient):
    """Brave Search 官方 API 客户端

    Args:
        api_key: Brave Search API Key，默认从 SOUWEN_BRAVE_API_KEY 读取
    """

    ENGINE_NAME = "brave_api"
    BASE_URL = "https://api.search.brave.com"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.brave_api_key
        if not self.api_key:
            raise ConfigError(
                "brave_api_key",
                "Brave Search API",
                "https://brave.com/search/api/",
            )
        super().__init__(base_url=self.BASE_URL)

    async def search(
        self,
        query: str,
        max_results: int = 20,
        country: str | None = None,
        search_lang: str | None = None,
        freshness: str | None = None,
    ) -> WebSearchResponse:
        """通过 Brave 官方 API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数 (最大20)
            country: 国家代码 (如 "CN", "US")
            search_lang: 搜索语言 (如 "zh-hans", "en")
            freshness: 时间过滤 ("pd"=过去24h, "pw"=过去一周, "pm"=过去一月)
        """
        params: dict[str, Any] = {
            "q": query,
            "count": min(max_results, 20),
        }
        if country:
            params["country"] = country
        if search_lang:
            params["search_lang"] = search_lang
        if freshness:
            params["freshness"] = freshness

        resp = await self.get(
            "/res/v1/web/search",
            params=params,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            },
        )
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Brave API 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        web_results = data.get("web", {}).get("results", [])
        for item in web_results:
            if len(results) >= max_results:
                break
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                continue
            raw: dict[str, Any] = {}
            if item.get("age"):
                raw["age"] = item["age"]
            if item.get("language"):
                raw["language"] = item["language"]
            if item.get("family_friendly"):
                raw["family_friendly"] = item["family_friendly"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_BRAVE_API,
                    title=title,
                    url=url,
                    snippet=item.get("description", "").strip(),
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Brave API 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_BRAVE_API,
            results=results,
            total_results=len(results),
        )
