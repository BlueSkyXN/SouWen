"""ScraperAPI 抓取 API 客户端

文件用途：
    ScraperAPI 网页抓取 API 客户端。通过 ScraperAPI 的代理轮换、JS 渲染、
    反爬绕过能力获取目标页面渲染后的原始 HTML，再借助共享提取工具
    `extract_from_html` 转为干净的 Markdown/文本内容，适用于难抓取站点。

函数/类清单：
    ScraperAPIClient（类）
        - 功能：ScraperAPI 抓取客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "scraperapi", BASE_URL = "https://api.scraperapi.com",
                  PROVIDER_NAME = "scraperapi", api_key (str) 来自配置的 API 密钥
        - 主要方法：fetch(url, timeout) -> FetchResult,
                  fetch_batch(urls, max_concurrency, timeout) -> FetchResponse

    ScraperAPIClient.__init__(api_key=None)
        - 功能：初始化 ScraperAPI 抓取客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_SCRAPERAPI_API_KEY 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    ScraperAPIClient.fetch(url, timeout=30.0) -> FetchResult
        - 功能：通过 ScraperAPI 抓取单个 URL，返回原始 HTML 后调用
                共享提取器 extract_from_html 转为 Markdown
        - 输入：url 目标网页 URL, timeout 超时秒数
        - 输出：FetchResult 包含提取的内容与元数据
        - 异常：所有异常封装到 FetchResult.error，避免中断批量任务

    ScraperAPIClient.fetch_batch(urls, max_concurrency=3, timeout=30.0) -> FetchResponse
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
    - souwen.web._html_extract: extract_from_html 共享 HTML→Markdown 提取工具

技术要点：
    - API 端点：GET https://api.scraperapi.com/
    - 认证方式：API Key 通过 query 参数 `api_key` 传递
    - 关键参数：url（目标 URL）、render=true（启用 JS 渲染）
    - 响应体：直接为渲染后的原始 HTML 字符串（非 JSON），使用 resp.text 读取
    - 内容提取：调用 extract_from_html(html, url) 统一转为 Markdown/Text
    - final_url：ScraperAPI 响应未提供最终 URL，降级使用原始 url
    - snippet：截取 content 前 500 字符
"""

from __future__ import annotations

import asyncio
import logging

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult
from souwen.web._html_extract import extract_from_html

logger = logging.getLogger("souwen.web.scraperapi")


class ScraperAPIClient(SouWenHttpClient):
    """ScraperAPI 抓取客户端

    Args:
        api_key: ScraperAPI API Key，默认从 SOUWEN_SCRAPERAPI_API_KEY 读取
    """

    ENGINE_NAME = "scraperapi"
    BASE_URL = "https://api.scraperapi.com"
    PROVIDER_NAME = "scraperapi"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("scraperapi", "scraperapi_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "scraperapi_api_key",
                "ScraperAPI",
                "https://www.scraperapi.com/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="scraperapi")

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """通过 ScraperAPI 抓取单个 URL

        Args:
            url: 目标网页 URL
            timeout: 超时秒数

        Returns:
            FetchResult 包含提取的内容与元数据
        """
        # API Key 通过 query 参数传递；启用 JS 渲染以提升对 SPA/动态站点的成功率
        params = {
            "api_key": self.api_key,
            "url": url,
            "render": "true",
        }
        try:
            # ScraperAPI 的根路径即为抓取端点，响应体直接是渲染后的 HTML
            resp = await self.get("/", params=params)
            html = resp.text or ""

            # 使用共享提取器把原始 HTML 转为 Markdown/Text 与元数据
            extracted = extract_from_html(html, url)
            content = extracted.get("content", "") or ""
            title = extracted.get("title", "") or ""
            content_format = extracted.get("content_format", "markdown") or "markdown"

            # snippet 截取内容前 500 字符
            snippet = content[:500] if content else ""

            return FetchResult(
                url=url,
                final_url=url,  # ScraperAPI 未返回最终 URL，降级回退到原始 URL
                title=title,
                content=content,
                content_format=content_format,
                source=self.PROVIDER_NAME,
                snippet=snippet,
                raw={
                    "provider": "scraperapi",
                    "status": resp.status_code,
                },
            )
        except Exception as exc:
            # 异常封装到 FetchResult.error，避免中断批量任务
            logger.warning("ScraperAPI fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "scraperapi"},
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
