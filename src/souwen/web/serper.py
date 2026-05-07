"""Serper Google SERP API 客户端

文件用途：
    Serper 搜索客户端。Serper 提供 Google 搜索结果的结构化 JSON API，
    包含 Knowledge Graph、People Also Ask 等丰富数据，支持多种搜索类型。

函数/类清单：
    SerperClient（类）
        - 功能：Serper Google SERP API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "serper", BASE_URL = "https://google.serper.dev",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, max_results, ...) -> WebSearchResponse

    SerperClient.__init__(api_key=None)
        - 功能：初始化 Serper 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_SERPER_API_KEY 读取
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    SerperClient.search(query, max_results=10, search_type="search", ...) -> WebSearchResponse
        - 功能：通过 Serper API 搜索 Google
        - 输入：query 搜索词, max_results 最大结果数（上限100）,
                search_type 搜索类型, country 国家代码, language 语言代码
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: str, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：POST /<search_type>，支持 search/news/images/scholar
    - X-API-KEY 请求头用于身份认证
    - 返回 organic 结果 + Knowledge Graph 附加数据
    - 支持国家和语言参数的地区化搜索
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.serper")


class SerperClient(SouWenHttpClient):
    """Serper Google SERP API 客户端

    Args:
        api_key: Serper API Key，默认从 SOUWEN_SERPER_API_KEY 读取
    """

    ENGINE_NAME = "serper"
    BASE_URL = "https://google.serper.dev"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("serper", "serper_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
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
        # 构建请求载荷
        payload: dict[str, Any] = {
            "q": query,
            "num": min(max_results, 100),  # API 最多返回 100 条
        }
        # 可选的地区化参数
        if country:
            payload["gl"] = country
        if language:
            payload["hl"] = language

        # 根据搜索类型构建端点，发送 POST 请求
        endpoint = f"/{search_type}"
        resp = await self.post(
            endpoint,
            json=payload,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
        )
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

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
            # 收集元数据：排名位置、日期、站点链接
            raw: dict[str, Any] = {}
            if item.get("position"):
                raw["position"] = item["position"]
            if item.get("date"):
                raw["date"] = item["date"]
            if item.get("sitelinks"):
                raw["sitelinks"] = item["sitelinks"]
            results.append(
                WebSearchResult(
                    source="serper",
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
            source="serper",
            results=results,
            total_results=len(results),
        )
