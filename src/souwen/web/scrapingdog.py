"""ScrapingDog Google 搜索 API 客户端

文件用途：
    ScrapingDog 搜索客户端。ScrapingDog 通过代理轮换和 JavaScript 渲染
    提供 Google 搜索结果的结构化 JSON API，适合需要稳定 Google 数据的场景。

函数/类清单：
    ScrapingDogClient（类）
        - 功能：ScrapingDog Google 搜索 API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "scrapingdog", BASE_URL = "https://api.scrapingdog.com",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, max_results) -> WebSearchResponse

    ScrapingDogClient.__init__(api_key=None)
        - 功能：初始化 ScrapingDog 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_SCRAPINGDOG_API_KEY 读取
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    ScrapingDogClient.search(query, max_results=10) -> WebSearchResponse
        - 功能：通过 ScrapingDog API 搜索 Google
        - 输入：query 搜索关键词, max_results 最大返回结果数
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
    - API 端点：GET /google，api_key 作为查询参数传递
    - 结果在 organic_data 字段中（不同于其他 API 的 organic_results）
    - 自动处理代理轮换和 JavaScript 渲染
    - 结果包含 position 排名位置元数据
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.scrapingdog")


class ScrapingDogClient(SouWenHttpClient):
    """ScrapingDog Google 搜索客户端

    Args:
        api_key: ScrapingDog API Key，默认从 SOUWEN_SCRAPINGDOG_API_KEY 读取
    """

    ENGINE_NAME = "scrapingdog"
    BASE_URL = "https://api.scrapingdog.com"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("scrapingdog", "scrapingdog_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "scrapingdog_api_key",
                "ScrapingDog",
                "https://www.scrapingdog.com/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="scrapingdog")

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> WebSearchResponse:
        """通过 ScrapingDog API 搜索 Google

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        # 构建查询参数，api_key 作为 URL 参数传递
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "results": max_results,
        }

        # 发送 GET 请求到 ScrapingDog /google 端点
        resp = await self.get("/google", params=params)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"ScrapingDog 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取自然搜索结果（注意：ScrapingDog 使用 organic_data 而非 organic_results）
        for item in data.get("organic_data", []):
            title = item.get("title", "").strip()
            url = item.get("link", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            # 收集元数据：排名位置
            raw: dict[str, Any] = {}
            if item.get("position"):
                raw["position"] = item["position"]
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_SCRAPINGDOG,
                    title=title,
                    url=url,
                    snippet=item.get("snippet", "").strip(),
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("ScrapingDog 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_SCRAPINGDOG,
            results=results,
            total_results=len(results),
        )
