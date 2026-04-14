"""Exa 语义搜索 API 客户端

Exa 使用自建神经索引进行语义搜索（非关键词匹配）。
适合查找相似内容、人物、公司、代码等。

接口: POST https://api.exa.ai/search
文档: https://docs.exa.ai/

特点：
- 语义搜索（理解查询意图，非纯关键词匹配）
- 自建索引（非 Google/Bing 驱动）
- 支持内容提取（返回清洗后的页面文本）
- 支持相似链接搜索（find_similar）
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.exa")


class ExaClient(SouWenHttpClient):
    """Exa 语义搜索客户端

    Args:
        api_key: Exa API Key，默认从 SOUWEN_EXA_API_KEY 读取
    """

    ENGINE_NAME = "exa"
    BASE_URL = "https://api.exa.ai"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("exa", "exa_api_key")
        if not self.api_key:
            raise ConfigError(
                "exa_api_key",
                "Exa",
                "https://dashboard.exa.ai/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="exa")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_type: str = "auto",
        use_autoprompt: bool = True,
        include_text: bool = True,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> WebSearchResponse:
        """通过 Exa API 语义搜索

        Args:
            query: 搜索关键词（支持自然语言描述）
            max_results: 最大返回结果数
            search_type: 搜索类型 "auto" / "neural" / "keyword"
            use_autoprompt: 是否让 Exa 优化查询
            include_text: 是否提取页面文本内容
            include_domains: 限定域名
            exclude_domains: 排除域名
        """
        payload: dict[str, Any] = {
            "query": query,
            "numResults": min(max_results, 100),
            "type": search_type,
            "useAutoprompt": use_autoprompt,
        }
        if include_text:
            payload["contents"] = {"text": True}
        if include_domains:
            payload["includeDomains"] = include_domains
        if exclude_domains:
            payload["excludeDomains"] = exclude_domains

        resp = await self.post(
            "/search",
            json=payload,
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Exa 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("results", []):
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                continue
            snippet = item.get("text", "").strip()[:500] if item.get("text") else ""
            raw: dict[str, Any] = {}
            if item.get("score"):
                raw["relevance_score"] = item["score"]
            if item.get("publishedDate"):
                raw["published_date"] = item["publishedDate"]
            if item.get("author"):
                raw["author"] = item["author"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_EXA,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Exa 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_EXA,
            results=results,
            total_results=len(results),
        )

    async def find_similar(
        self,
        url: str,
        max_results: int = 10,
    ) -> WebSearchResponse:
        """查找与给定 URL 相似的页面

        Args:
            url: 目标 URL
            max_results: 最大返回结果数
        """
        payload: dict[str, Any] = {
            "url": url,
            "numResults": min(max_results, 100),
            "contents": {"text": True},
        }

        resp = await self.post(
            "/findSimilar",
            json=payload,
            headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Exa find_similar 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        for item in data.get("results", []):
            title = item.get("title", "").strip()
            result_url = item.get("url", "").strip()
            if not title or not result_url:
                continue
            snippet = item.get("text", "").strip()[:500] if item.get("text") else ""
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_EXA,
                    title=title,
                    url=result_url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw={"score": item.get("score")},
                )
            )

        return WebSearchResponse(
            query=f"similar:{url}",
            source=SourceType.WEB_EXA,
            results=results,
            total_results=len(results),
        )
