"""Brave Search 官方 API 客户端

文件用途：
    Brave Search 官方 REST API 客户端（区别于爬虫方式）。
    提供官方 API 的稳定性和功能丰富性，支持搜索参数自定义。

函数/类清单：
    BraveApiClient（类）
        - 功能：Brave Search 官方 API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "brave_api", BASE_URL = "https://api.search.brave.com",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, max_results, country, search_lang, freshness) -> WebSearchResponse

    BraveApiClient.__init__(api_key=None)
        - 功能：初始化 Brave API 客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_BRAVE_API_KEY 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    BraveApiClient.search(query, max_results=20, country=None, search_lang=None, freshness=None) -> WebSearchResponse
        - 功能：通过 Brave 官方 API 搜索
        - 输入：query 搜索词, max_results 最大结果数(默认20), country 国家代码(如"CN"),
                search_lang 搜索语言(如"zh-hans"), freshness 时间过滤("pd"/"pw"/"pm")
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.exceptions: ConfigError, ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：/res/v1/web/search
    - 请求头包含 X-Subscription-Token 用于身份认证
    - 响应 JSON 解析错误使用 ParseError 包装
    - 支持国家、语言、时间过滤等搜索参数
    - API 免费档限额 2000 次/月
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
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("brave_api", "brave_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "brave_api_key",
                "Brave Search API",
                "https://brave.com/search/api/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="brave_api")

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
        # 构建请求参数
        params: dict[str, Any] = {
            "q": query,
            "count": min(max_results, 20),  # API 最多返回 20 条
        }
        # 可选参数仅在提供时添加
        if country:
            params["country"] = country
        if search_lang:
            params["search_lang"] = search_lang
        if freshness:
            params["freshness"] = freshness

        # 发送 GET 请求到 Brave API
        resp = await self.get(
            "/res/v1/web/search",
            params=params,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,  # API 认证令牌
            },
        )
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Brave API 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取 web 搜索结果
        web_results = data.get("web", {}).get("results", [])
        for item in web_results:
            if len(results) >= max_results:
                break
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            # 收集额外元数据（如发布时间、语言、家庭友好标志）
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
