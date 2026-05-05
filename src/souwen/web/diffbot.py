"""Diffbot 文章提取 API 客户端

文件用途：
    Diffbot 结构化数据提取 API 客户端。基于 AI/ML 理解网页结构，
    擅长文章/新闻/学术内容的纯文本提取，返回干净的文章正文与元数据
    （标题、作者、发布时间、站点名、标签等）。

函数/类清单：
    DiffbotClient（类）
        - 功能：Diffbot Article API 客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "diffbot", BASE_URL = "https://api.diffbot.com",
                  PROVIDER_NAME = "diffbot", api_token (str) 来自配置的 API Token
        - 主要方法：fetch(url, timeout) -> FetchResult,
                  fetch_batch(urls, max_concurrency, timeout) -> FetchResponse

    DiffbotClient.__init__(api_token=None)
        - 功能：初始化 Diffbot 客户端，验证 API Token 可用性
        - 输入：api_token (str|None) API 令牌，默认从 SOUWEN_DIFFBOT_API_TOKEN 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效的 API Token 时抛出

    DiffbotClient.fetch(url, timeout=30.0) -> FetchResult
        - 功能：通过 Diffbot Article API 提取单个 URL 的结构化文章内容
        - 输入：url 目标网页 URL, timeout 超时秒数
        - 输出：FetchResult 包含纯文本正文、标题、作者、发布时间等元数据
        - 异常：所有异常封装到 FetchResult.error 中，不向上抛出

    DiffbotClient.fetch_batch(urls, max_concurrency=5, timeout=30.0) -> FetchResponse
        - 功能：批量抓取多个 URL，使用 asyncio.Semaphore 控制并发
        - 输入：urls URL 列表, max_concurrency 最大并发数, timeout 单 URL 超时
        - 输出：FetchResponse 聚合结果（含成功/失败统计）

模块依赖：
    - logging: 日志记录
    - typing: 类型注解
    - souwen.config: 获取 API Token 和全局配置
    - souwen.core.exceptions: ConfigError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: FetchResult, FetchResponse 数据模型

技术要点：
    - API 端点：GET /v3/article（Diffbot Article API，专为文章内容优化）
    - 认证方式：API Token 通过 query 参数 token 传递（非 Header）
    - timeout 通过毫秒形式传递给 Diffbot 服务端
    - 响应结构 objects[0] 为主文章对象，包含 text/title/author/date 等字段
    - final_url 优先取 resolvedPageUrl（重定向后的最终地址），降级到 pageUrl
    - 发布时间优先取 date，缺失时回退到 estimatedDate（Diffbot 推断时间）
    - 内容格式为 "text"（Diffbot 返回纯文本，非 Markdown）
    - 当 objects 为空时返回带 error 的 FetchResult（页面可能非文章类型）
"""

from __future__ import annotations

import logging

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.diffbot")


class DiffbotClient(SouWenHttpClient):
    """Diffbot 文章提取客户端

    Args:
        api_token: Diffbot API Token，默认从 SOUWEN_DIFFBOT_API_TOKEN 读取
    """

    ENGINE_NAME = "diffbot"
    BASE_URL = "https://api.diffbot.com"
    PROVIDER_NAME = "diffbot"

    def __init__(self, api_token: str | None = None):
        # 从参数或配置读取 API Token
        config = get_config()
        self.api_token = api_token or config.resolve_api_key("diffbot", "diffbot_api_token")
        if not self.api_token:
            # 未提供有效的 API Token 时抛出配置错误
            raise ConfigError(
                "diffbot_api_token",
                "Diffbot",
                "https://www.diffbot.com/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="diffbot")

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """通过 Diffbot Article API 抓取单个 URL

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（会转为毫秒传递给 Diffbot）

        Returns:
            FetchResult 包含提取的纯文本内容与元数据
        """
        # API Token 通过 query 参数传递（Diffbot 约定）
        params = {
            "token": self.api_token,
            "url": url,
            "timeout": str(int(timeout * 1000)),  # Diffbot timeout 单位为毫秒
        }
        try:
            # 发送 GET 请求到 Article API
            resp = await self.get("/v3/article", params=params)
            data = resp.json()

            # objects 为提取出的对象数组，文章类型时 objects[0] 即文章主体
            objects = data.get("objects", [])
            if not objects:
                # 页面可能非文章类型（如纯列表页、视频页）
                return FetchResult(
                    url=url,
                    final_url=url,
                    source=self.PROVIDER_NAME,
                    error="Diffbot 未提取到内容（页面可能非文章类型）",
                    raw={"provider": "diffbot"},
                )

            article = objects[0]
            # 提取核心字段
            content = article.get("text", "") or ""
            title = article.get("title", "") or ""
            # final_url 优先取 resolvedPageUrl（重定向后的最终地址）
            final_url = article.get("resolvedPageUrl") or article.get("pageUrl") or url
            author = article.get("author")
            # 发布时间优先取 date，缺失时回退到 estimatedDate
            date = article.get("date") or article.get("estimatedDate")
            # snippet 取正文前 500 字符
            snippet = content[:500] if content else ""

            return FetchResult(
                url=url,
                final_url=final_url,
                title=title,
                content=content,
                content_format="text",  # Diffbot 返回纯文本
                source=self.PROVIDER_NAME,
                snippet=snippet,
                published_date=date,
                author=author,
                raw={
                    "provider": "diffbot",
                    "type": article.get("type"),
                    "siteName": article.get("siteName"),
                    "tags": article.get("tags", []),
                },
            )
        except Exception as exc:
            # 异常封装到 FetchResult.error，避免中断批量任务
            logger.warning("Diffbot fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "diffbot"},
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 5,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数（Diffbot 付费计划速率较宽松，默认 5）
            timeout: 每个 URL 超时

        Returns:
            FetchResponse 聚合结果
        """
        import asyncio

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
