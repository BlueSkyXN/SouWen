"""Perplexity AI 搜索 API 客户端

文件用途：
    Perplexity AI 搜索客户端。Perplexity 使用 Sonar 模型提供 AI 生成的
    综合性答案（带引用来源），而非传统搜索结果列表，适合问答型查询。

函数/类清单：
    PerplexityClient（类）
        - 功能：Perplexity Sonar API 客户端，通过 Chat Completions 接口搜索
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "perplexity", BASE_URL = "https://api.perplexity.ai",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, max_results, model) -> WebSearchResponse

    PerplexityClient.__init__(api_key=None)
        - 功能：初始化 Perplexity 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_PERPLEXITY_API_KEY 读取
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    PerplexityClient.search(query, max_results=10, model="sonar") -> WebSearchResponse
        - 功能：通过 Perplexity Sonar API 搜索
        - 输入：query 搜索关键词或自然语言问题, max_results 未使用,
                model 模型名（sonar/sonar-pro 等）
        - 输出：WebSearchResponse 包含 AI 生成的答案
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.exceptions: ConfigError, ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：POST /v1/chat/completions，兼容 OpenAI Chat API 格式
    - Authorization 头使用 Bearer token 认证
    - 返回单条 AI 生成的答案而非传统搜索结果列表
    - 答案可包含 citations 引用来源列表
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
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("perplexity", "perplexity_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "perplexity_api_key",
                "Perplexity",
                "https://docs.perplexity.ai/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="perplexity")
        # 设置 Authorization 头（Bearer token 认证）
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
        # 构建 Chat Completions 请求载荷（兼容 OpenAI 格式）
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "user", "content": query},
            ],
        }

        # 发送 POST 请求到 Perplexity Chat API
        resp = await self.post("/v1/chat/completions", json=payload)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Perplexity 响应解析失败: {e}") from e

        # Perplexity 返回 AI 生成的答案，从 choices[0].message.content 提取
        choices = data.get("choices", [])
        answer = ""
        if choices:
            message = choices[0].get("message", {})
            answer = message.get("content", "").strip()

        results: list[WebSearchResult] = []
        if answer:
            # 构建结果，将 AI 答案作为 snippet，引用来源存入 raw
            raw: dict[str, Any] = {}
            citations = data.get("citations")
            if citations:
                raw["citations"] = citations  # 引用来源列表
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
