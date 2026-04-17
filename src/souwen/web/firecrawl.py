"""Firecrawl 搜索 API 客户端

文件用途：
    Firecrawl 搜索与内容提取 API 客户端。提供搜索 + 网页抓取一体化，
    支持返回 Markdown 格式页面内容，自动过滤导航、广告等噪声。

函数/类清单：
    FirecrawlClient（类）
        - 功能：Firecrawl 搜索客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "firecrawl", BASE_URL = "https://api.firecrawl.dev",
                  api_key (str) 来自配置的 API 密钥，headers 包含 Authorization 令牌
        - 主要方法：search(query, max_results) -> WebSearchResponse

    FirecrawlClient.__init__(api_key=None)
        - 功能：初始化 Firecrawl 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_FIRECRAWL_API_KEY 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    FirecrawlClient.search(query, max_results=10) -> WebSearchResponse
        - 功能：通过 Firecrawl API 搜索并抓取页面内容
        - 输入：query 搜索词, max_results 最大结果数（默认10）
        - 输出：WebSearchResponse 包含搜索结果和 Markdown 内容
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.exceptions: ConfigError, ParseError 异常
    - souwen.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：/v1/search
    - Authorization 头使用 Bearer token 认证
    - 搜索选项包括返回格式（markdown）和主内容模式
    - 原始数据（raw）包含 Markdown 格式的页面内容
    - 标题和描述优先使用 metadata 字段，降级到顶级字段
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import SourceType, WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.firecrawl")


class FirecrawlClient(SouWenHttpClient):
    """Firecrawl 搜索客户端

    Args:
        api_key: Firecrawl API Key，默认从 SOUWEN_FIRECRAWL_API_KEY 读取
    """

    ENGINE_NAME = "firecrawl"
    BASE_URL = "https://api.firecrawl.dev"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("firecrawl", "firecrawl_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "firecrawl_api_key",
                "Firecrawl",
                "https://www.firecrawl.dev/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="firecrawl")
        # 设置 Authorization 头（Bearer token）
        self.headers["Authorization"] = f"Bearer {self.api_key}"

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> WebSearchResponse:
        """通过 Firecrawl API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            
        Returns:
            WebSearchResponse 包含搜索结果和 Markdown 内容
        """
        # 构建请求载荷
        payload: dict[str, Any] = {
            "query": query,
            "limit": max_results,
            "scrapeOptions": {
                "formats": ["markdown"],  # 返回 Markdown 格式的页面内容
                "onlyMainContent": True,  # 仅提取主内容（过滤导航、广告）
            },
        }

        # 发送 POST 请求到 Firecrawl API
        resp = await self.post("/v1/search", json=payload)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.exceptions import ParseError

            raise ParseError(f"Firecrawl 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取搜索结果
        for item in data.get("data", []):
            # 元数据字段（title、description）优先级高于顶级字段
            metadata = item.get("metadata", {})
            title = (metadata.get("title") or item.get("title", "")).strip()
            url = (item.get("url", "")).strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            # 获取页面描述
            snippet = (metadata.get("description") or item.get("description", "")).strip()
            # 收集原始数据（Markdown 内容）
            raw: dict[str, Any] = {}
            if item.get("markdown"):
                raw["markdown"] = item["markdown"]  # 清洗后的页面 Markdown
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_FIRECRAWL,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Firecrawl 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_FIRECRAWL,
            results=results,
            total_results=len(results),
        )
