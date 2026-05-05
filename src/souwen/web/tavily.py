"""Tavily AI 研究搜索 API 客户端

文件用途：
    Tavily AI 搜索客户端。Tavily 专为 AI Agent 设计，提供自动查询扩展、
    去重和页面内容提取，支持 AI 答案摘要和原始内容返回。

函数/类清单：
    TavilyClient（类）
        - 功能：Tavily AI 搜索 API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "tavily", BASE_URL = "https://api.tavily.com",
                  api_key (str) 来自配置的 API 密钥
        - 主要方法：search(query, max_results, ...) -> WebSearchResponse,
                  extract(urls, timeout) -> FetchResponse

    TavilyClient.__init__(api_key=None)
        - 功能：初始化 Tavily 搜索客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_TAVILY_API_KEY 读取
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    TavilyClient.search(query, max_results=10, search_depth="basic", ...) -> WebSearchResponse
        - 功能：通过 Tavily API 执行搜索
        - 输入：query 搜索词, max_results 最大结果数（API 上限20）,
                search_depth 搜索深度, include_answer 是否返回 AI 答案,
                include_raw_content 是否返回原始内容,
                include_domains/exclude_domains 域名过滤
        - 输出：WebSearchResponse 包含搜索结果
        - 异常：ParseError API 响应解析失败时抛出

    TavilyClient.extract(urls, timeout=30.0) -> FetchResponse
        - 功能：通过 Tavily Extract API 批量提取 URL 内容
        - 输入：urls 目标 URL 列表, timeout 超时秒数
        - 输出：FetchResponse 包含提取结果（含成功与失败条目）
        - 异常：ParseError API 响应解析失败时抛出

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse,
                    FetchResult, FetchResponse 数据模型

技术要点：
    - API 端点：POST /search，api_key 放在请求体中
    - content 字段是提取后的页面内容（比传统 snippet 更丰富）
    - 支持 AI 生成的答案摘要（include_answer=True）
    - 搜索深度分 basic（快速）和 advanced（深度）两档
    - Extract 端点：POST /extract，批量提取 URL 原始内容
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult, SourceType, WebSearchResponse, WebSearchResult

logger = logging.getLogger("souwen.web.tavily")


class TavilyClient(SouWenHttpClient):
    """Tavily AI 搜索客户端

    Args:
        api_key: Tavily API Key，默认从 SOUWEN_TAVILY_API_KEY 读取
    """

    ENGINE_NAME = "tavily"
    BASE_URL = "https://api.tavily.com"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("tavily", "tavily_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "tavily_api_key",
                "Tavily",
                "https://app.tavily.com/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="tavily")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        include_answer: bool = False,
        include_raw_content: bool = False,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> WebSearchResponse:
        """通过 Tavily API 搜索

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数 (最大20)
            search_depth: 搜索深度 "basic" 或 "advanced"
            include_answer: 是否返回 AI 生成的答案摘要
            include_raw_content: 是否返回页面原始内容
            include_domains: 限定域名列表
            exclude_domains: 排除域名列表
        """
        # 构建请求载荷，api_key 放在请求体中
        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": min(max_results, 20),  # API 最多返回 20 条
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
        }
        # 可选的域名过滤参数
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        # 发送 POST 请求到 Tavily API
        resp = await self.post("/search", json=payload)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

            raise ParseError(f"Tavily 响应解析失败: {e}") from e

        results: list[WebSearchResult] = []
        # 提取搜索结果
        for item in data.get("results", []):
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            if not title or not url:
                # 跳过不完整的结果
                continue
            # Tavily 的 content 字段是提取后的页面内容（比 snippet 更丰富）
            snippet = item.get("content", "").strip()
            # 收集元数据
            raw: dict[str, Any] = {}
            if item.get("score"):
                raw["relevance_score"] = item["score"]  # 搜索相关性分数
            if item.get("raw_content"):
                raw["raw_content"] = item["raw_content"]  # 页面原始内容
            results.append(
                WebSearchResult(
                    source=SourceType.WEB_TAVILY,
                    title=title,
                    url=url,
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                    raw=raw,
                )
            )

        # 提取 Tavily 的 AI 答案摘要（如果有）
        answer = data.get("answer")
        raw_resp: dict[str, Any] = {}
        if answer:
            raw_resp["ai_answer"] = answer  # AI 生成的答案摘要

        logger.info("Tavily 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_TAVILY,
            results=results,
            total_results=len(results),
        )

    async def extract(self, urls: list[str], timeout: float = 30.0) -> FetchResponse:
        """通过 Tavily Extract API 批量提取 URL 内容

        Args:
            urls: 目标 URL 列表
            timeout: 超时秒数

        Returns:
            FetchResponse 包含提取结果
        """
        # 构建请求载荷，api_key 放在请求体中
        payload = {"api_key": self.api_key, "urls": urls}
        resp = await self.post("/extract", json=payload)
        try:
            # 解析 JSON 响应
            data = resp.json()
        except Exception as e:
            from souwen.core.exceptions import ParseError

            raise ParseError(f"Tavily Extract 响应解析失败: {e}") from e

        results: list[FetchResult] = []
        # 提取成功结果
        for item in data.get("results", []):
            url = item.get("url", "")
            raw_content = item.get("raw_content", "")
            results.append(
                FetchResult(
                    url=url,
                    final_url=url,
                    title="",
                    content=raw_content,
                    content_format="text",
                    source="tavily",
                    snippet=raw_content[:500] if raw_content else "",
                    raw={"provider": "tavily_extract"},
                )
            )
        # 处理失败结果
        for item in data.get("failed_results", []):
            fail_url = item.get("url", "") if isinstance(item, dict) else str(item)
            results.append(
                FetchResult(
                    url=fail_url,
                    final_url=fail_url,
                    source="tavily",
                    error=item.get("error", "extraction failed")
                    if isinstance(item, dict)
                    else "extraction failed",
                    raw={"provider": "tavily_extract"},
                )
            )

        ok = sum(1 for r in results if r.error is None)
        logger.info("Tavily Extract 提取 %d 个 URL，成功 %d 个", len(urls), ok)

        return FetchResponse(
            urls=urls,
            results=results,
            total=len(results),
            total_ok=ok,
            total_failed=len(results) - ok,
            provider="tavily",
        )
