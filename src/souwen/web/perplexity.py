"""Perplexity Sonar 搜索 API 客户端

Perplexity 提供基于 AI 的搜索 API（Sonar 模型），返回带引用的 AI 生成答案。
与传统搜索不同，Perplexity 返回的是综合性答案而非链接列表。

接口: POST https://api.perplexity.ai/v1/chat/completions
文档: https://docs.perplexity.ai/

特点：
- AI 生成的综合性答案
- 自动附带引用来源
- 基于 Sonar 模型（实时联网搜索）
- 适合需要直接答案而非链接列表的场景
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.perplexity")


class PerplexityClient(SouWenHttpClient):
    """Perplexity Sonar 搜索客户端

    Args:
        api_key: Perplexity API Key，默认从 SOUWEN_PERPLEXITY_API_KEY 读取
    """

    ENGINE_NAME = "perplexity"
    BASE_URL = "https://api.perplexity.ai"

    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("perplexity", "perplexity_api_key")
        if not self.api_key:
            raise ConfigError(
                "perplexity_api_key",
                "Perplexity",
                "https://docs.perplexity.ai/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="perplexity")
        self.headers["Authorization"] = f"Bearer {self.api_key}"

    async def search(
        self,
        query: str,
        max_results: int = 10,
        model: str = "sonar",
    ) -> WebSearchResponse:
        """通过 Perplexity Sonar API 搜索

        Perplexity 返回 AI 生成的综合性答案（带引用），而非传统搜索结果列表。

        Args:
            query: 搜索关键词或自然语言问题
            max_results: 未使用（Perplexity 返回单个 AI 答案）
            model: 使用的模型 "sonar" / "sonar-pro" 等
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "user", "content": query},
            ],
        }

        resp = await self.post("/v1/chat/completions", json=payload)
        try:
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Perplexity 响应解析失败: {e}") from e

        # Perplexity 返回 AI 生成的答案，而非传统搜索结果
        choices = data.get("choices", [])
        answer = ""
        if choices:
            message = choices[0].get("message", {})
            answer = message.get("content", "").strip()

        results: list[WebSearchResult] = []
        if answer:
            raw: dict[str, Any] = {}
            citations = data.get("citations")
            if citations:
                raw["citations"] = citations
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_PERPLEXITY,
                    title=f"Perplexity AI: {query}",
                    url="https://www.perplexity.ai/",
                    snippet=answer,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Perplexity 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_PERPLEXITY,
            results=results,
            total_results=len(results),
        )
