"""Linkup 搜索 API 客户端

文件用途：
    Linkup 搜索 API 客户端。提供结构化的网页搜索，支持多种搜索深度和输出类型，
    适合需要快速获取结构化搜索结果的场景。

函数/类清单：
    LinkupClient（类）
        - 功能：Linkup 搜索客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "linkup", BASE_URL = "https://api.linkup.so",
                  api_key (str) 来自配置的 API 密钥，headers 包含 Authorization 令牌
        - 主要方法：search(query, max_results, depth, output_type) -> WebSearchResponse

    LinkupClient.__init__(api_key=None)
        - 功能：初始化 Linkup 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_LINKUP_API_KEY 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    LinkupClient.search(query, max_results=10, depth="standard", output_type="searchResults") -> WebSearchResponse
        - 功能：通过 Linkup API 搜索
        - 输入：query 搜索词, max_results 最大结果数, depth 搜索深度 ("standard"/"deep"),
                output_type 输出类型 ("searchResults"/"sourcedAnswer"/等)
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
    - API 端点：/v1/search
    - Authorization 头使用 Bearer token 认证
    - 支持搜索深度：standard（标准）、deep（深度）
    - 输出类型控制返回数据格式
    - 标题优先使用 name 字段，降级到 title；内容优先使用 content，降级到 snippet
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.linkup")


class LinkupClient(SouWenHttpClient):
    """Linkup 搜索客户端

    Args:
        api_key: Linkup API Key，默认从 SOUWEN_LINKUP_API_KEY 读取
    """

    ENGINE_NAME = "linkup"
    BASE_URL = "https://api.linkup.so"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("linkup", "linkup_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "linkup_api_key",
                "Linkup",
                "https://www.linkup.so/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="linkup")
        # 设置 Authorization 头（Bearer token）
        self.headers["Authorization"] = f"Bearer {self.api_key}"

    async def search(
        self,
        query: str,
        max_results: int = 10,
        depth: str = "standard",
        output_type: str = "searchResults",
    ) -> WebSearchResponse:
        """通过 Linkup API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
            depth: 搜索深度 "standard" 或 "deep"
            output_type: 输出类型 "searchResults" / "sourcedAnswer" 等

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # 构建请求载荷
        payload: dict[str, Any] = {
            "q": query,
            "depth": depth,  # standard 或 deep
            "outputType": output_type,  # 控制返回数据格式
            "maxResults": max_results,
        }

        # 发送 POST 请求到 Linkup API
        resp = await self.post("/v1/search", json=payload)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

            raise ParseError(f"Linkup 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取搜索结果
        for item in data.get("results", []):
            # 标题优先使用 name，降级到 title
            title = (item.get("name") or item.get("title", "")).strip()
            url = item.get("url", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            # 内容优先使用 content，降级到 snippet
            snippet = (item.get("content") or item.get("snippet", "")).strip()
            # 原始数据为空（Linkup API 结构相对简洁）
            raw: dict[str, Any] = {}
            results.append(
                WebSearchResult(
                    source="linkup",
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Linkup 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="linkup",
            results=results,
            total_results=len(results),
        )
