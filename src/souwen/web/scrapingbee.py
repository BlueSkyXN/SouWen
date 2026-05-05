"""ScrapingBee 抓取 API 客户端

文件用途：
    ScrapingBee 网页抓取 API 客户端。提供代理轮换、JS 渲染与反爬绕过能力，
    返回目标页面的渲染后原始 HTML，再通过共享 HTML 提取工具
    （souwen.web._html_extract.extract_from_html）转换为 Markdown / Text，
    适用于需要浏览器渲染或代理绕过的难抓取站点。

函数/类清单：
    ScrapingBeeClient（类）
        - 功能：ScrapingBee 抓取客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "scrapingbee", BASE_URL = "https://app.scrapingbee.com",
                  PROVIDER_NAME = "scrapingbee", api_key (str) 来自配置的 API 密钥
        - 主要方法：fetch(url, timeout) -> FetchResult,
                  fetch_batch(urls, max_concurrency, timeout) -> FetchResponse

    ScrapingBeeClient.__init__(api_key=None)
        - 功能：初始化 ScrapingBee 抓取客户端，验证 API Key 可用性
        - 输入：api_key (str|None) API 密钥，默认从 SOUWEN_SCRAPINGBEE_API_KEY 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效的 API Key 时抛出

    ScrapingBeeClient.fetch(url, timeout=30.0) -> FetchResult
        - 功能：通过 ScrapingBee /api/v1/ 端点抓取单个 URL，提取为 Markdown
        - 输入：url 目标网页 URL, timeout 超时秒数（毫秒级传入 API）
        - 输出：FetchResult 包含提取的内容与元数据
        - 异常：所有异常封装到 FetchResult.error，避免中断批量任务

    ScrapingBeeClient.fetch_batch(urls, max_concurrency=3, timeout=30.0) -> FetchResponse
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
    - souwen.web._html_extract: 共享 HTML→Markdown/Text 提取工具

技术要点：
    - API 端点：GET /api/v1/
    - API Key 通过 query 参数 `api_key` 传递（非 Header）
    - 默认启用 render_js=true（JS 渲染）以提升复杂站点抓取成功率
    - timeout 以毫秒形式传给 ScrapingBee（int(timeout * 1000)）
    - 响应体直接是渲染后的原始 HTML（Content-Type: text/html），需 resp.text 读取
    - 内容提取委托 _html_extract.extract_from_html(html, url) 完成
    - ScrapingBee 不返回最终 URL，final_url 默认回退为请求 URL
    - snippet 截取 content 前 500 字符
"""

from __future__ import annotations

import asyncio
import logging

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult
from souwen.web._html_extract import extract_from_html

logger = logging.getLogger("souwen.web.scrapingbee")


class ScrapingBeeClient(SouWenHttpClient):
    """ScrapingBee 抓取客户端

    Args:
        api_key: ScrapingBee API Key，默认从 SOUWEN_SCRAPINGBEE_API_KEY 读取
    """

    ENGINE_NAME = "scrapingbee"
    BASE_URL = "https://app.scrapingbee.com"
    PROVIDER_NAME = "scrapingbee"

    def __init__(self, api_key: str | None = None):
        # 从参数或配置读取 API Key
        config = get_config()
        self.api_key = api_key or config.resolve_api_key("scrapingbee", "scrapingbee_api_key")
        if not self.api_key:
            # 未提供有效的 API Key 时抛出配置错误
            raise ConfigError(
                "scrapingbee_api_key",
                "ScrapingBee",
                "https://www.scrapingbee.com/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="scrapingbee")

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """通过 ScrapingBee /api/v1/ 端点抓取单个 URL

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（API 内部以毫秒接收）

        Returns:
            FetchResult 包含提取的内容与元数据
        """
        # API Key 通过 query 参数传递；启用 JS 渲染以处理动态页面
        params = {
            "api_key": self.api_key,
            "url": url,
            "render_js": "true",
            "timeout": str(int(timeout * 1000)),
        }
        try:
            # 发送 GET 请求到 ScrapingBee /api/v1/ 端点
            resp = await self.get("/api/v1/", params=params)
            # ScrapingBee 响应体直接是渲染后的 HTML（非 JSON）
            html = resp.text or ""

            # 委托共享提取工具完成 HTML → Markdown/Text 转换
            extracted = extract_from_html(html, url)
            content = extracted.get("content", "") or ""
            title = extracted.get("title", "") or ""
            content_format = extracted.get("content_format", "markdown") or "markdown"

            # snippet 截取内容前 500 字符
            snippet = content[:500] if content else ""

            return FetchResult(
                url=url,
                # ScrapingBee 不返回最终 URL，回退到请求 URL
                final_url=url,
                title=title,
                content=content,
                content_format=content_format,
                source=self.PROVIDER_NAME,
                snippet=snippet,
                raw={
                    "provider": "scrapingbee",
                    "status": resp.status_code,
                },
            )
        except Exception as exc:
            # 异常封装到 FetchResult.error，避免中断批量任务
            logger.warning("ScrapingBee fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "scrapingbee"},
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
