"""Apify Website Content Crawler 抓取客户端

文件用途：
    Apify 平台抓取客户端，调用官方 "Website Content Crawler" actor 通过
    同步运行端点 (run-sync-get-dataset-items) 抓取网页并直接返回结构化的
    Markdown / 文本内容与元数据，免去 HTML 解析步骤。支持单 URL 抓取与
    批量抓取（同一 actor run 内并行爬取多个 URL，效率高于多次串行调用）。

函数/类清单：
    ApifyClient（类）
        - 功能：Apify 抓取客户端，通过 HTTP 调用官方 REST API
        - 继承：SouWenHttpClient（HTTP 客户端基类）
        - 关键属性：ENGINE_NAME = "apify", BASE_URL = "https://api.apify.com",
                  PROVIDER_NAME = "apify", api_token (str) 来自配置的 API Token
        - 主要方法：fetch(url, timeout) -> FetchResult,
                  fetch_batch(urls, max_concurrency, timeout) -> FetchResponse

    ApifyClient.__init__(api_token=None)
        - 功能：初始化 Apify 抓取客户端，验证 API Token 可用性
        - 输入：api_token (str|None) API Token，默认从 SOUWEN_APIFY_API_TOKEN 读取
        - 输出：实例
        - 异常：ConfigError 未提供有效 Token 时抛出

    ApifyClient.fetch(url, timeout=30.0) -> FetchResult
        - 功能：通过 run-sync-get-dataset-items 同步运行 actor 抓取单个 URL
        - 输入：url 目标网页 URL, timeout 超时秒数（同时作为 actor 最大运行时间）
        - 输出：FetchResult 包含 markdown/text 内容与元数据
        - 异常：所有异常封装到 FetchResult.error，避免中断批量任务

    ApifyClient.fetch_batch(urls, max_concurrency=2, timeout=30.0) -> FetchResponse
        - 功能：批量抓取，优先使用单次 actor run 同时爬取多个 URL；失败则回退到并发单抓
        - 输入：urls URL 列表, max_concurrency 回退路径并发数, timeout 单 URL 超时
        - 输出：FetchResponse 聚合结果（含成功/失败统计）

模块依赖：
    - asyncio: 异步并发控制（Semaphore + gather）
    - logging: 日志记录
    - souwen.config: 获取 API Token 和全局配置
    - souwen.core.exceptions: ConfigError 异常
    - souwen.core.http_client: SouWenHttpClient HTTP 客户端基类
    - souwen.models: FetchResponse, FetchResult 数据模型

技术要点：
    - API 端点：POST /v2/acts/apify~website-content-crawler/run-sync-get-dataset-items
    - API Token 通过 query 参数 `token` 传递（非 Header）
    - run-sync 端点会阻塞直到 actor 运行结束，最长不超过 query 参数 `timeout` 秒
    - 请求体使用 actor 输入 schema：startUrls / maxCrawlPages / maxCrawlDepth / crawlerType
    - maxCrawlDepth=0 禁止 actor 跟随链接，确保只抓取传入的 URL
    - crawlerType="cheerio" 使用快速 HTML 抓取（不渲染 JS），开销最低
    - 批量抓取在同一次 actor run 中并行爬取，比多次单抓显著节省启动时间与配额
    - 响应是 dataset items 数组，每个 item 含 url/text/markdown/metadata
    - 内容提取优先级：item.markdown > item.text
    - title/author 取自 item.metadata
    - 批量超时上限 300 秒，避免极端情况下一直挂起
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

from souwen.config import get_config
from souwen.core.exceptions import ConfigError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.apify")

# Website Content Crawler actor 的同步运行端点
_ACTOR_SYNC_PATH = "/v2/acts/apify~website-content-crawler/run-sync-get-dataset-items"


class ApifyClient(SouWenHttpClient):
    """Apify 抓取客户端

    Args:
        api_token: Apify API Token，默认从 SOUWEN_APIFY_API_TOKEN 读取
    """

    ENGINE_NAME = "apify"
    BASE_URL = "https://api.apify.com"
    PROVIDER_NAME = "apify"

    def __init__(self, api_token: str | None = None):
        # 从参数或配置读取 API Token
        config = get_config()
        self.api_token = api_token or config.resolve_api_key("apify", "apify_api_token")
        if not self.api_token:
            # 未提供有效的 API Token 时抛出配置错误
            raise ConfigError(
                "apify_api_token",
                "Apify",
                "https://apify.com/",
            )
        super().__init__(base_url=self.BASE_URL, source_name="apify")

    def _build_actor_path(self, timeout_s: int) -> str:
        # SouWenHttpClient.post 不直接接受 query params，这里把 token/timeout 拼到 URL 上
        query = urlencode({"token": self.api_token, "timeout": str(timeout_s)})
        return f"{_ACTOR_SYNC_PATH}?{query}"

    @staticmethod
    def _item_to_result(
        item: dict,
        original_url: str,
        provider: str,
    ) -> FetchResult:
        """将 actor 返回的单个 dataset item 转换为 FetchResult"""
        # 内容优先取 markdown，其次 text
        markdown = item.get("markdown") or ""
        text = item.get("text") or ""
        content = markdown or text or ""
        content_format = "markdown" if markdown else "text"

        metadata = item.get("metadata") or {}
        title = metadata.get("title", "") or ""
        author = metadata.get("author")

        # final_url 取 item 中实际抓取到的 URL（处理重定向），降级回退原始 URL
        final_url = item.get("url", original_url) or original_url

        snippet = content[:500] if content else ""

        return FetchResult(
            url=original_url,
            final_url=final_url,
            title=title,
            author=author,
            content=content,
            content_format=content_format,
            source=provider,
            snippet=snippet,
            raw={
                "provider": provider,
                "language": metadata.get("languageCode"),
                "description": metadata.get("description"),
            },
        )

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """通过 Apify Website Content Crawler 抓取单个 URL

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（同时作为 actor 最大运行时间）

        Returns:
            FetchResult 包含提取的内容与元数据
        """
        timeout_s = max(1, int(timeout))
        # actor 输入：仅抓取传入的单个 URL，不跟随链接，使用快速 cheerio 爬虫
        body = {
            "startUrls": [{"url": url}],
            "maxCrawlPages": 1,
            "maxCrawlDepth": 0,
            "crawlerType": "cheerio",
        }
        try:
            resp = await self.post(self._build_actor_path(timeout_s), json=body)
            data = resp.json()
            # 同步端点返回 dataset items 数组
            items = data if isinstance(data, list) else []
            if not items:
                # actor 运行成功但没产生任何 item（站点拒绝或无内容）
                return FetchResult(
                    url=url,
                    final_url=url,
                    source=self.PROVIDER_NAME,
                    error="apify: actor returned no items",
                    raw={"provider": "apify"},
                )
            return self._item_to_result(items[0], url, self.PROVIDER_NAME)
        except Exception as exc:
            # 异常封装到 FetchResult.error，避免中断批量任务
            logger.warning("Apify fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "apify"},
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 2,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        优先在同一次 actor run 中并行爬取所有 URL（更省启动开销与配额）。
        若批量调用失败，则回退到逐 URL 抓取（受 max_concurrency 限制）。

        Args:
            urls: URL 列表
            max_concurrency: 回退路径下的最大并发数
            timeout: 单 URL 超时秒数（批量时整体超时取 timeout * len(urls)，封顶 300）

        Returns:
            FetchResponse 聚合结果
        """
        if not urls:
            return FetchResponse(
                urls=[],
                results=[],
                total=0,
                total_ok=0,
                total_failed=0,
                provider=self.PROVIDER_NAME,
            )

        # 批量整体超时：按 URL 数量线性放大，但封顶 300 秒以防挂死
        batch_timeout_s = min(300, max(1, int(timeout * len(urls))))
        body = {
            "startUrls": [{"url": u} for u in urls],
            "maxCrawlPages": len(urls),
            "maxCrawlDepth": 0,
            "crawlerType": "cheerio",
        }

        try:
            resp = await self.post(self._build_actor_path(batch_timeout_s), json=body)
            data = resp.json()
            items = data if isinstance(data, list) else []

            # 按 URL 建立索引：actor 返回顺序未必与请求一致，需要按 url 字段匹配
            # 同一 URL 可能产生多条 item（理论上单页爬取不会，但保守只取首个）
            by_url: dict[str, dict] = {}
            for it in items:
                if not isinstance(it, dict):
                    continue
                u = it.get("url")
                if u and u not in by_url:
                    by_url[u] = it

            results: list[FetchResult] = []
            for original in urls:
                item = by_url.get(original)
                if item is None:
                    # 某些 URL 在 actor run 中失败或被跳过，构造错误结果占位
                    results.append(
                        FetchResult(
                            url=original,
                            final_url=original,
                            source=self.PROVIDER_NAME,
                            error="apify: url missing from actor results",
                            raw={"provider": "apify"},
                        )
                    )
                else:
                    results.append(self._item_to_result(item, original, self.PROVIDER_NAME))

            ok = sum(1 for r in results if r.error is None)
            return FetchResponse(
                urls=urls,
                results=results,
                total=len(results),
                total_ok=ok,
                total_failed=len(results) - ok,
                provider=self.PROVIDER_NAME,
            )
        except Exception as exc:
            # 批量调用失败：回退到逐 URL 抓取（与其他 provider 一致的并发模型）
            logger.warning("Apify batch run failed, falling back to sequential fetch: err=%s", exc)

            sem = asyncio.Semaphore(max_concurrency)

            async def _fetch_one(u: str) -> FetchResult:
                async with sem:
                    return await self.fetch(u, timeout=timeout)

            results = list(await asyncio.gather(*[_fetch_one(u) for u in urls]))
            ok = sum(1 for r in results if r.error is None)
            return FetchResponse(
                urls=urls,
                results=results,
                total=len(results),
                total_ok=ok,
                total_failed=len(results) - ok,
                provider=self.PROVIDER_NAME,
            )
