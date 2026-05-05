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
        - 主要方法：search(query, max_results) -> WebSearchResponse,
                  scrape(url, timeout) -> FetchResult,
                  scrape_batch(urls, max_concurrency, timeout) -> FetchResponse

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

    FirecrawlClient.scrape(url, timeout=30.0) -> FetchResult
        - 功能：通过 Firecrawl Scrape API 抓取单个 URL，提取 Markdown 内容
        - 输入：url 目标网页 URL, timeout 超时秒数
        - 输出：FetchResult 包含提取的 Markdown 内容与元数据
        - 异常：ParseError API 响应解析失败时抛出（其余异常封装到 FetchResult.error）

    FirecrawlClient.scrape_batch(urls, max_concurrency=3, timeout=30.0) -> FetchResponse
        - 功能：批量抓取多个 URL，使用 asyncio.Semaphore 控制并发
        - 输入：urls URL 列表, max_concurrency 最大并发数, timeout 单 URL 超时
        - 输出：FetchResponse 聚合结果（含成功/失败统计）

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ConfigError, ParseError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse, FetchResult, FetchResponse 数据模型

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
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult, SourceType, WebSearchResult, WebSearchResponse

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
            from souwen.core.exceptions import ParseError

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

    async def scrape(self, url: str, timeout: float = 30.0) -> FetchResult:
        """通过 Firecrawl Scrape API 抓取单个 URL

        Args:
            url: 目标网页 URL
            timeout: 超时秒数

        Returns:
            FetchResult 包含提取的 Markdown 内容
        """
        # 构建请求载荷（仅请求 Markdown 格式）
        payload: dict[str, Any] = {
            "url": url,
            "formats": ["markdown"],
        }
        try:
            # 发送 POST 请求到 Firecrawl Scrape API
            resp = await self.post("/v1/scrape", json=payload)
            try:
                # 解析 JSON 响应
                data = resp.json()
            except Exception as e:
                from souwen.core.exceptions import ParseError

                raise ParseError(f"Firecrawl Scrape 响应解析失败: {e}") from e

            # 提取数据与元数据
            scrape_data = data.get("data", {})
            metadata = scrape_data.get("metadata", {})
            markdown = scrape_data.get("markdown", "")
            title = metadata.get("title", "")
            # final_url 优先取 metadata.url，降级到 sourceURL，最后回退到原始 URL
            final_url = metadata.get("url") or metadata.get("sourceURL") or url
            # snippet 优先使用 description，否则截取 markdown 前 500 字符
            snippet = (metadata.get("description") or markdown[:500]).strip()

            return FetchResult(
                url=url,
                final_url=final_url,
                title=title,
                content=markdown,
                content_format="markdown",
                source="firecrawl",
                snippet=snippet,
                raw={"provider": "firecrawl_scrape"},
            )
        except Exception as exc:
            # 异常封装到 FetchResult.error，避免中断批量任务
            logger.warning("Firecrawl scrape failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source="firecrawl",
                error=str(exc),
                raw={"provider": "firecrawl_scrape"},
            )

    async def scrape_batch(
        self,
        urls: list[str],
        max_concurrency: int = 3,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数
            timeout: 每个 URL 超时

        Returns:
            FetchResponse 聚合结果
        """
        import asyncio

        # 使用 Semaphore 控制最大并发
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.scrape(u, timeout=timeout)

        # 并发抓取所有 URL
        results = await asyncio.gather(*[_fetch_one(u) for u in urls])
        result_list = list(results)
        # 统计成功/失败数量
        ok = sum(1 for r in result_list if r.error is None)
        return FetchResponse(
            urls=urls,
            results=result_list,
            total=len(result_list),
            total_ok=ok,
            total_failed=len(result_list) - ok,
            provider="firecrawl",
        )
