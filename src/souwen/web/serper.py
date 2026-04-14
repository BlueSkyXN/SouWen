"""Serper Google SERP API 客户端

Serper 提供 Google 搜索结果的结构化 JSON 接口。
包含 Knowledge Graph、People Also Ask 等丰富数据。

接口: POST https://google.serper.dev/search
文档: https://serper.dev/docs

特点：
- Google 搜索结果的结构化 JSON
- 包含 Knowledge Graph 数据
- 支持 Google News / Images / Scholar 搜索
- 价格低 (~$1-2/千次)
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.serper")


class SerperClient(SouWenHttpClient):
    """Serper Google SERP API 客户端

    Args:
        api_key: Serper API Key，默认从 SOUWEN_SERPER_API_KEY 读取
    """

    ENGINE_NAME = "serper"
    BASE_URL = "https://google.serper.dev"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("serper", "serper_api_key")
        if not self.api_key:
            raise ConfigError(
                "serper_api_key",
                "Serper",
                "https://serper.dev/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="serper")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_type: str = "search",
        country: str | None = None,
        language: str | None = None,
    ) -> WebSearchResponse:
        """通过 Serper API 搜索 Google

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数 (最大100)
            search_type: 搜索类型 "search" / "news" / "images" / "scholar"
            country: 国家代码 (如 "cn", "us")
            language: 语言代码 (如 "zh-cn", "en")
        """
        payload: dict[str, Any] = {
            "q": query,
            "num": min(max_results, 100),
        }
        if country:
            payload["gl"] = country
        if language:
            payload["hl"] = language

        endpoint = f"/{search_type}"
        resp = await self.post(
            endpoint,
            json=payload,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
        )
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Serper 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # Serper 返回 organic 结果
        for item in data.get("organic", []):
            if len(results) >= max_results:
                break
            title = item.get("title", "").strip()
            url = item.get("link", "").strip()
            if not title or not url:
                continue
            raw: dict[str, Any] = {}
            if item.get("position"):
                raw["position"] = item["position"]
            if item.get("date"):
                raw["date"] = item["date"]
            if item.get("sitelinks"):
                raw["sitelinks"] = item["sitelinks"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_SERPER,
                    title=title,
                    url=url,
                    snippet=item.get("snippet", "").strip(),
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        # Knowledge Graph 数据（如果有）
        kg = data.get("knowledgeGraph")
        raw_resp: dict[str, Any] = {}
        if kg:
            raw_resp["knowledge_graph"] = kg

        logger.info("Serper 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_SERPER,
            results=results,
            total_results=len(results),
        )
