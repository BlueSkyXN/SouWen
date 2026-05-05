"""Scrapfly 抓取 API 客户端

文件用途：
    Scrapfly 网页抓取 API 客户端。提供高成功率的网页抓取能力，
    支持 JS 渲染、反爬绕过（ASP）、AI 内容提取（readability/article 等模型），
    返回干净的 Markdown / 文本 / HTML 内容，适用于难抓取站点。

函数/类清单：
    ScrapflyClient（类）
        - 功能：Scrapfly 抓取客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "scrapfly", BASE_URL = "https://api.scrapfly.io",
                  PROVIDER_NAME = "scrapfly", api_key (str) 来自配置的 API 密钥
        - 主要方法：fetch(url, timeout) -> FetchResult,
                  fetch_batch(urls, max_concurrency, timeout) -> FetchResponse

    ScrapflyClient.__init__(api_key=None)
        - 功能：初始化 Scrapfly 抓取客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_SCRAPFLY_API_KEY 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    ScrapflyClient.fetch(url, timeout=30.0) -> FetchResult
        - 功能：通过 Scrapfly /scrape API 抓取单个 URL，提取 Markdown 内容
        - 输入：url 目标网页 URL, timeout 超时秒数（毫秒级传入 API）
        - 输出：FetchResult 包含提取的内容与元数据
        - 异常：所有异常封装到 FetchResult.error，避免中断批量任务

    ScrapflyClient.fetch_batch(urls, max_concurrency=3, timeout=30.0) -> FetchResponse
        - 功能：批量抓取多个 URL，使用 asyncio.Semaphore 控制并发
        - 输入：urls URL 列表, max_concurrency 最大并发数, timeout 单 URL 超时
        - 输出：FetchResponse 聚合结果（含成功/失败统计）

模块依赖：
    - asyncio: 异步并发控制（Semaphore + gather）
    - logging: 日志记录
    - souwen.config: 获取 API Key 和全局配置
    - souwen.core.exceptions: ConfigError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: FetchResponse, FetchResult 数据模型

技术要点：
    - API 端点：GET /scrape
    - API Key 通过 query 参数 `key` 传递（非 Header）
    - 默认启用 render_js=true（JS 渲染）和 asp=true（反爬绕过）
    - format=markdown 请求 Markdown 格式输出
    - timeout 以毫秒形式传给 Scrapfly（int(timeout * 1000)）
    - 响应结构：result.{content, content_type, status_code, url, extracted_data}
    - 内容提取优先级：extracted_data.markdown > extracted_data.text > result.content
    - title 来自 extracted_data.title（如启用 extraction_model）
    - final_url 取 result.url（重定向后的最终 URL）
"""

from __future__ import annotations

import asyncio
import logging

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.scrapfly")


class ScrapflyClient(SouWenHttpClient):
    """Scrapfly 抓取客户端

    Args:
        api_key: Scrapfly API Key，默认从 SOUWEN_SCRAPFLY_API_KEY 读取
    """

    ENGINE_NAME = "scrapfly"
    BASE_URL = "https://api.scrapfly.io"
    PROVIDER_NAME = "scrapfly"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("scrapfly", "scrapfly_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "scrapfly_api_key",
                "Scrapfly",
                "https://scrapfly.io/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="scrapfly")

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """通过 Scrapfly /scrape API 抓取单个 URL

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（API 内部以毫秒接收）

        Returns:
            FetchResult 包含提取的内容与元数据
        """
        # API Key 通过 query 参数传递；启用 JS 渲染与反爬绕过以提高成功率
        params = {
            "key": self.api_key,
            "url": url,
            "render_js": "true",
            "asp": "true",
            "format": "markdown",
            "timeout": str(int(timeout * 1000)),
        }
        try:
            # 发送 GET 请求到 Scrapfly /scrape 端点
            resp = await self.get("/scrape", params=params)
            data = resp.json()
            result_data = data.get("result", {}) or {}

            # 内容提取优先级：extracted_data.markdown > extracted_data.text > result.content
            content = ""
            extracted = result_data.get("extracted_data")
            if extracted and isinstance(extracted, dict):
                content = extracted.get("markdown") or extracted.get("text") or ""
            if not content:
                content = result_data.get("content", "") or ""

            # final_url 取响应中的最终 URL（处理重定向），降级回退到原始 URL
            final_url = result_data.get("url", url) or url

            # title 仅在启用 extraction_model 时由 extracted_data 提供
            title = ""
            if extracted and isinstance(extracted, dict):
                title = extracted.get("title", "") or ""

            # snippet 截取内容前 500 字符
            snippet = content[:500] if content else ""

            return FetchResult(
                url=url,
                final_url=final_url,
                title=title,
                content=content,
                content_format="markdown",
                source=self.PROVIDER_NAME,
                snippet=snippet,
                raw={
                    "provider": "scrapfly",
                    "status": result_data.get("status_code"),
                },
            )
        except Exception as exc:
            # 异常封装到 FetchResult.error，避免中断批量任务
            logger.warning("Scrapfly fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "scrapfly"},
            )

    async def fetch_batch(
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
        # 使用 Semaphore 控制最大并发
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.fetch(u, timeout=timeout)

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
            provider=self.PROVIDER_NAME,
        )
