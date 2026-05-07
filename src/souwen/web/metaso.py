"""Metaso 搜索 API 客户端

文件用途：
    Metaso 搜索客户端。支持文档(document)、网页(webpage)、学术(scholar)三种搜索范围，
    以及 Reader API 用于网页内容提取。

函数/类清单：
    MetasoClient（类）
        - 功能：Metaso 搜索 API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "metaso", BASE_URL = "https://metaso.cn/api/v1",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, scope, max_results, ...) -> WebSearchResponse,
                  reader(url, timeout) -> FetchResponse

    MetasoClient.__init__(api_key=None)
        - 功能：初始化 Metaso 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_METASO_API_KEY 读取
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    MetasoClient.search(query, scope="webpage", max_results=10, ...) -> WebSearchResponse
        - 功能：通过 Metaso API 执行搜索
        - 输入：query 搜索词, scope 搜索范围（document/webpage/scholar）,
                max_results 最大结果数（API 上限100）,
                include_summary 是否返回摘要,
                include_raw_content 是否返回原始内容,
                concise_snippet 是否使用简洁片段
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

    MetasoClient.reader(url, timeout=30.0) -> FetchResponse
        - 功能：通过 Metaso Reader API 提取 URL 内容
        - 输入：url 目标 URL, timeout 超时秒数
        - 输出：FetchResponse 包含提取结果
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: str, WebSearchResult, WebSearchResponse,
                    FetchResult, FetchResponse 数据模型

技术要点：
    - API 端点：POST /search，Authorization: Bearer <api_key>
    - 支持三种搜索范围：document（文档）、webpage（网页）、scholar（学术）
    - Reader 端点：POST /reader，返回纯文本内容
    - 搜索参数：includeSummary, size, conciseSnippet, includeRawContent
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, ParseError, SouWenError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.metaso")


class MetasoClient(SouWenHttpClient):
    """Metaso 搜索客户端

    Args:
        api_key: Metaso API Key，默认从 SOUWEN_METASO_API_KEY 读取
    """

    ENGINE_NAME = "metaso"
    BASE_URL = "https://metaso.cn/api/v1"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("metaso", "metaso_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "metaso_api_key",
                "Metaso",
                "https://metaso.cn/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="metaso")

    async def search(
        self,
        query: str,
        scope: Literal["document", "webpage", "scholar"] = "webpage",
        max_results: int = 10,
        include_summary: bool = False,
        include_raw_content: bool = False,
        concise_snippet: bool = False,
    ) -> WebSearchResponse:
        """通过 Metaso API 搜索

        Args:
            query: 搜索关键词
            scope: 搜索范围 "document" / "webpage" / "scholar"
            max_results: 最大返回结果数 (最大100)
            include_summary: 是否返回摘要
            include_raw_content: 是否返回原始内容（仅 webpage）
            concise_snippet: 是否使用简洁片段

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # 构建请求载荷
        payload: dict[str, Any] = {
            "q": query,
            "scope": scope,
            "includeSummary": include_summary,
            "size": min(max_results, 100),  # API 最多返回 100 条
            "conciseSnippet": concise_snippet,
        }
        # webpage 范围支持原始内容
        if scope == "webpage" and include_raw_content:
            payload["includeRawContent"] = include_raw_content

        # 发送 POST 请求到 Metaso API
        resp = await self.post(
            "/search",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            raise ParseError(f"Metaso 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取搜索结果
        for item in data.get("data", []):
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            # Metaso 的 snippet 字段是提取后的页面摘要
            snippet = item.get("snippet", "").strip()
            # 收集元数据
            raw: dict[str, Any] = {}
            if item.get("summary"):
                raw["summary"] = item["summary"]  # 搜索摘要
            if item.get("rawContent"):
                raw["raw_content"] = item["rawContent"]  # 页面原始内容
            if item.get("publishedDate"):
                raw["published_date"] = item["publishedDate"]  # 发布日期
            if item.get("author"):
                raw["author"] = item["author"]  # 作者
            if item.get("source"):
                raw["source_name"] = item["source"]  # 来源名称

            results.append(
                WebSearchResult(
                    source="metaso",
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        logger.info("Metaso 返回 %d 条结果 (query=%s, scope=%s)", len(results), query, scope)

        return WebSearchResponse(
            query=query,
            source="metaso",
            results=results,
            total_results=len(results),
        )

    async def reader(self, url: str, timeout: float = 30.0) -> FetchResponse:
        """通过 Metaso Reader API 提取 URL 内容

        Args:
            url: 目标 URL
            timeout: 超时秒数

        Returns:
            FetchResponse 包含提取结果
        """
        # 构建请求载荷
        payload = {"url": url}

        try:
            # 发送 POST 请求到 Reader API
            resp = await self.post(
                "/reader",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "text/plain",
                    "Content-Type": "application/json",
                },
            )

            # Reader API 返回纯文本
            content = resp.text

            results = [
                FetchResult(
                    url=url,
                    final_url=url,
                    title="",
                    content=content,
                    content_format="text",
                    source="metaso",
                    snippet=content[:500] if content else "",
                    raw={"provider": "metaso_reader"},
                )
            ]

            logger.info("Metaso Reader 成功提取 URL: %s", url)

            return FetchResponse(
                urls=[url],
                results=results,
                total=1,
                total_ok=1,
                total_failed=0,
                provider="metaso",
            )
        except (httpx.HTTPError, SouWenError, OSError, ValueError) as e:
            logger.warning("Metaso Reader 提取失败: url=%s err=%s", url, e)

            results = [
                FetchResult(
                    url=url,
                    final_url=url,
                    source="metaso",
                    error=str(e),
                    raw={"provider": "metaso_reader"},
                )
            ]

            return FetchResponse(
                urls=[url],
                results=results,
                total=1,
                total_ok=0,
                total_failed=1,
                provider="metaso",
            )
