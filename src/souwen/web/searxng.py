"""SearXNG 自部署隐私元搜索引擎

文件用途：
    SearXNG 搜索客户端。SearXNG 是隐私优先的开源元搜索引擎，
    聚合多个搜索引擎结果，无用户追踪，需用户自行部署实例。

函数/类清单：
    SearXNGClient（类）
        - 功能：SearXNG JSON API 客户端，通过 HTTP 调用自部署实例
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "searxng", instance_url 自部署实例地址
        - 主要方法：search(query, max_results, ...) -> WebSearchResponse

    SearXNGClient.__init__(instance_url=None)
        - 功能：初始化 SearXNG 搜索客户端，验证实例 URL 可用性
        - 输入：instance_url (str|None) 实例地址，默认从 SOUWEN_SEARXNG_URL 读取
        - 异常：ConfigError 未提供实例 URL 时抛出

    SearXNGClient.search(query, max_results=20, engines=None, ...) -> WebSearchResponse
        - 功能：通过 SearXNG JSON API 执行搜索
        - 输入：query 搜索词, max_results 最大结果数,
                engines 指定引擎（逗号分隔）, categories 分类,
                language 语言
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取实例 URL 配置
    - souwen.exceptions: ConfigError, ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：GET /search?format=json，通过 format=json 获取 JSON 响应
    - 支持指定后端引擎（如 google,bing,duckduckgo）
    - 每条结果自带 engine 字段标识来源引擎
    - total_results 优先使用 API 返回的 number_of_results
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
        # 从参数或配置读取 SearXNG 实例 URL
        config = get_config()
        self.instance_url = (
            instance_url
            or config.resolve_base_url("searxng")
            or config.resolve_api_key("searxng", "searxng_url")
            or ""
        ).rstrip("/")
        if not self.instance_url:
            # 未提供实例 URL 时抛出配置错误
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
        # 构建查询参数，format=json 指定 JSON 响应格式
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "language": language,
        }
        # 可选的引擎和分类筛选
        if engines:
            params["engines"] = engines
        if categories:
            params["categories"] = categories

        # 发送 GET 请求到 SearXNG 实例
        resp = await self.get("/search", params=params)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"SearXNG 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取搜索结果
        for item in data.get("results", []):
            if len(results) >= max_results:
                break
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_SEARXNG,
                    title=title,
                    url=url,
                    snippet=item.get("content", "").strip(),
                    engine=item.get("engine", self.ENGINE_NAME),  # 使用结果自带的引擎标识
                )
            )

        logger.info("SearXNG 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_SEARXNG,
            results=results,
            total_results=data.get("number_of_results", 0)
            or len(results),  # 优先使用 API 返回的总数
        )
