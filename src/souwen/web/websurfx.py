"""Websurfx 自部署隐私元搜索引擎

文件用途：
    Websurfx 搜索客户端。Websurfx 是隐私优先的开源元搜索引擎（Rust 实现），
    聚合多个搜索引擎结果，无用户追踪，需用户自行部署实例。

函数/类清单：
    WebsurfxClient（类）
        - 功能：Websurfx JSON API 客户端，通过 HTTP 调用自部署实例
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "websurfx", instance_url 自部署实例地址
        - 主要方法：search(query, max_results) -> WebSearchResponse

    WebsurfxClient.__init__(instance_url=None)
        - 功能：初始化 Websurfx 搜索客户端，验证实例 URL 可用性
        - 输入：instance_url (str|None) 实例地址，默认从 SOUWEN_WEBSURFX_URL 读取
        - 异常：ConfigError 未提供实例 URL 时抛出

    WebsurfxClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：通过 Websurfx JSON API 执行搜索
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取实例 URL 配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: str, WebSearchResult, WebSearchResponse 数据模型

技术要点：
    - API 端点：GET /search?format=json，通过 format=json 获取 JSON 响应
    - 描述字段尝试 description 和 content 两个字段降级
    - 需要用户自部署 Websurfx 实例并提供 URL
    - 与 SearXNG 类似但使用 Rust 实现，性能更优
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.websurfx")


class WebsurfxClient(SouWenHttpClient):
    """Websurfx JSON API 客户端

    Args:
        instance_url: Websurfx 实例 URL (如 http://localhost:8080)
                     默认从 SOUWEN_WEBSURFX_URL 环境变量读取
    """

    ENGINE_NAME = "websurfx"

    def __init__(self, instance_url: str | None = None):
        # 从参数或配置读取 Websurfx 实例 URL
        config = get_config()
        self.instance_url = (
            instance_url
            or config.resolve_base_url("websurfx")
            or config.resolve_api_key("websurfx", "websurfx_url")
            or ""
        ).rstrip("/")
        if not self.instance_url:
            # 未提供实例 URL 时抛出配置错误
            raise ConfigError(
                "websurfx_url",
                "Websurfx",
                "https://github.com/neon-mmd/websurfx",
            )
        super().__init__(base_url=self.instance_url, source_name="websurfx")

    async def search(
        self,
        query: str,
        max_results: int = 20,
    ) -> WebSearchResponse:
        """通过 Websurfx JSON API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        # 构建查询参数，format=json 指定 JSON 响应格式
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
        }

        # 发送 GET 请求到 Websurfx 实例
        resp = await self.get("/search", params=params)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

            raise ParseError(f"Websurfx 响应解析失败: {e}") from e

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
            # 描述字段降级：优先 description，降级到 content
            snippet = (item.get("description") or item.get("content") or "").strip()
            results.append(
                WebSearchResult(
                    source="websurfx",
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                )
            )

        logger.info("Websurfx 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="websurfx",
            results=results,
            total_results=len(results),
        )
