"""SerpAPI 多引擎搜索 API 客户端

文件用途：
    SerpAPI 搜索客户端。SerpAPI 提供 Google、Bing、Yahoo、Baidu 等多种
    搜索引擎的结构化 JSON 结果，支持 Knowledge Graph 和 Related Questions。

函数/类清单：
    SerpApiClient（类）
        - 功能：SerpAPI 搜索 API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "serpapi", BASE_URL = "https://serpapi.com",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, max_results, engine) -> WebSearchResponse

    SerpApiClient.__init__(api_key=None)
        - 功能：初始化 SerpAPI 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_SERPAPI_API_KEY 读取
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    SerpApiClient.search(query, max_results=10, engine="google") -> WebSearchResponse
        - 功能：通过 SerpAPI 执行搜索
        - 输入：query 搜索词, max_results 最大结果数,
                engine 搜索引擎（google/bing/yahoo/baidu 等）
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：GET /search，api_key 作为查询参数传递
    - 支持多引擎切换（通过 engine 参数指定搜索引擎）
    - 返回 organic_results + Knowledge Graph + Related Questions
    - 结果包含 position、date、source 等元数据
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.serpapi")


class SerpApiClient(SouWenHttpClient):
    """SerpAPI 搜索客户端

    Args:
        api_key: SerpAPI API Key，默认从 SOUWEN_SERPAPI_API_KEY 读取
    """

    ENGINE_NAME = "serpapi"
    BASE_URL = "https://serpapi.com"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("serpapi", "serpapi_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "serpapi_api_key",
                "SerpAPI",
                "https://serpapi.com/manage-api-key",
            )
        super().__init__(base_url=self.BASE_URL, source_name="serpapi")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        engine: str = "google",
    ) -> WebSearchResponse:
        """通过 SerpAPI 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            engine: 搜索引擎 "google" / "bing" / "yahoo" / "baidu" 等
        """
        # 构建查询参数，api_key 作为 URL 参数传递
        params: dict[str, Any] = {
            "engine": engine,
            "q": query,
            "api_key": self.api_key,
            "num": max_results,
        }

        # 发送 GET 请求到 SerpAPI
        resp = await self.get("/search", params=params)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

            raise ParseError(f"SerpAPI 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取自然搜索结果（organic_results）
        for item in data.get("organic_results", []):
            title = item.get("title", "").strip()
            url = item.get("link", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            # 收集元数据：排名位置、日期、来源
            raw: dict[str, Any] = {}
            if item.get("position"):
                raw["position"] = item["position"]
            if item.get("date"):
                raw["date"] = item["date"]
            if item.get("source"):
                raw["source"] = item["source"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_SERPAPI,
                    title=title,
                    url=url,
                    snippet=item.get("snippet", "").strip(),
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        # Knowledge Graph 和 Related Questions
        kg = data.get("knowledge_graph")
        related = data.get("related_questions")
        raw_resp: dict[str, Any] = {}
        if kg:
            raw_resp["knowledge_graph"] = kg
        if related:
            raw_resp["related_questions"] = related

        logger.info("SerpAPI 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_SERPAPI,
            results=results,
            total_results=len(results),
        )
