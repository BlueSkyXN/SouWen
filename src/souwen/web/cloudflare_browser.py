"""Cloudflare Browser Rendering 抓取客户端

文件用途：
    Cloudflare Browser Rendering REST API 客户端。利用 Cloudflare 边缘网络
    的无头浏览器渲染页面并直接返回 Markdown 内容（/markdown 端点），适用于
    需要 JS 渲染、又希望避开自建浏览器集群的场景，且 Markdown 输出对 LLM
    友好。当 /markdown 返回为空时，自动回退到 /content 拉取 HTML 并通过
    本地 trafilatura/html2text 链路二次提取。

函数/类清单：
    CloudflareBrowserClient（类）
        - 功能：Cloudflare Browser Rendering 抓取客户端
        - 继承：SouWenHttpClient
        - 关键属性：ENGINE_NAME = "cloudflare_browser",
                  BASE_URL = "https://api.cloudflare.com",
                  PROVIDER_NAME = "cloudflare",
                  api_token (str) Bearer 鉴权令牌,
                  account_id (str) Cloudflare 账户 ID
        - 主要方法：fetch(url, timeout) -> FetchResult,
                  fetch_batch(urls, max_concurrency, timeout) -> FetchResponse

    CloudflareBrowserClient.__init__(api_token=None, account_id=None)
        - 功能：初始化客户端，校验 API Token 与 Account ID
        - 输入：api_token (str|None) Cloudflare API Token,
              account_id (str|None) Cloudflare 账户 ID
        - 输出：实例
        - 异常：ConfigError 当 token 或 account_id 缺失时抛出

    CloudflareBrowserClient.fetch(url, timeout=30.0) -> FetchResult
        - 功能：调用 /browser-rendering/markdown 抓取并直接获得 Markdown；
              若结果为空则回退到 /content 端点拉取 HTML 并本地提取
        - 输入：url 目标网页 URL, timeout 超时秒数
        - 输出：FetchResult 包含 Markdown / 文本内容与元数据
        - 异常：所有异常封装到 FetchResult.error，避免中断批量任务

    CloudflareBrowserClient.fetch_batch(urls, max_concurrency=3, timeout=30.0) -> FetchResponse
        - 功能：批量抓取多个 URL，asyncio.Semaphore 控制并发
        - 输入：urls URL 列表, max_concurrency 最大并发, timeout 单 URL 超时
        - 输出：FetchResponse 聚合结果

模块依赖：
    - asyncio: 异步并发控制
    - logging: 日志记录
    - souwen.config: 读取 API Token / Account ID 与全局配置
    - souwen.exceptions: ConfigError
    - souwen.http_client: SouWenHttpClient 基类
    - souwen.models: FetchResponse, FetchResult
    - souwen.web._html_extract: HTML → Markdown/文本 回退提取

技术要点：
    - API 端点：
        POST /client/v4/accounts/{account_id}/browser-rendering/markdown
        POST /client/v4/accounts/{account_id}/browser-rendering/content（回退）
    - 鉴权：Authorization: Bearer <API_TOKEN> 请求头
    - 请求体：{"url": url}（可扩展 gotoOptions / viewport / userAgent）
    - 响应结构：{"result": "...", "success": bool, "errors": [...], "messages": [...]}
    - 优先使用 /markdown（无需本地解析 HTML，对 LLM 友好）
    - 当 /markdown 的 result 为空字符串时，回退 /content + extract_from_html
    - title 从 Markdown 首个 `# ` 行提取（回退路径用 HTML 提取的 title）
    - final_url 直接取请求 URL（Cloudflare /markdown 不返回重定向信息）
"""

from __future__ import annotations

import asyncio
import logging

from souwen.config import get_config
from souwen.exceptions import ConfigError
from souwen.http_client import SouWenHttpClient
from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.cloudflare_browser")


class CloudflareBrowserClient(SouWenHttpClient):
    """Cloudflare Browser Rendering 抓取客户端

    Args:
        api_token: Cloudflare API Token（需 "Browser Rendering – Edit" 权限）
        account_id: Cloudflare 账户 ID
    """

    ENGINE_NAME = "cloudflare_browser"
    BASE_URL = "https://api.cloudflare.com"
    PROVIDER_NAME = "cloudflare"

    def __init__(
        self,
        api_token: str | None = None,
        account_id: str | None = None,
    ):
        # 从参数或配置读取鉴权信息
        config = get_config()
        self.api_token = api_token or config.resolve_api_key("cloudflare", "cloudflare_api_token")
        self.account_id = account_id or getattr(config, "cloudflare_account_id", None)

        if not self.api_token:
            raise ConfigError(
                "cloudflare_api_token",
                "Cloudflare Browser Rendering",
                "https://dash.cloudflare.com/",
            )
        if not self.account_id:
            raise ConfigError(
                "cloudflare_account_id",
                "Cloudflare Browser Rendering",
                "https://dash.cloudflare.com/",
            )

        super().__init__(
            base_url=self.BASE_URL,
            source_name="cloudflare_browser",
            headers={"Authorization": f"Bearer {self.api_token}"},
        )

    @staticmethod
    def _extract_title_from_markdown(markdown: str) -> str:
        """从 Markdown 首个一级标题（`# `）行提取标题"""
        if not markdown:
            return ""
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""

    @staticmethod
    def _format_api_errors(data: dict) -> str:
        """将 Cloudflare 响应中的 errors 数组格式化为可读字符串"""
        errors = data.get("errors") or []
        if not errors:
            return "Cloudflare API returned success=false with no error detail"
        parts = []
        for err in errors:
            if isinstance(err, dict):
                code = err.get("code", "")
                message = err.get("message", "")
                parts.append(f"[{code}] {message}".strip())
            else:
                parts.append(str(err))
        return "; ".join(parts)

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL，优先返回 Markdown

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（保留参数，由底层 httpx 客户端控制实际超时）

        Returns:
            FetchResult 包含 Markdown / 文本内容与元数据
        """
        markdown_path = f"/client/v4/accounts/{self.account_id}/browser-rendering/markdown"
        content_path = f"/client/v4/accounts/{self.account_id}/browser-rendering/content"
        body = {"url": url}

        try:
            # 1) 优先调用 /markdown
            resp = await self.post(markdown_path, json=body)
            data = resp.json()

            if not data.get("success", False):
                err_msg = self._format_api_errors(data)
                logger.warning(
                    "Cloudflare /markdown returned success=false: url=%s err=%s",
                    url,
                    err_msg,
                )
                # 不直接返回错误，继续尝试 /content 回退路径
                content = ""
            else:
                content = data.get("result", "") or ""

            content_format = "markdown"
            title = self._extract_title_from_markdown(content)

            # 2) /markdown 为空时回退 /content + 本地 HTML 提取
            if not content:
                logger.info(
                    "Cloudflare /markdown empty, falling back to /content: url=%s",
                    url,
                )
                resp2 = await self.post(content_path, json=body)
                data2 = resp2.json()

                if not data2.get("success", False):
                    err_msg2 = self._format_api_errors(data2)
                    return FetchResult(
                        url=url,
                        final_url=url,
                        source=self.PROVIDER_NAME,
                        error=f"Cloudflare /content failed: {err_msg2}",
                        raw={"provider": "cloudflare_browser"},
                    )

                html = data2.get("result", "") or ""
                # 延迟导入避免无回退时的不必要开销
                from souwen.web._html_extract import extract_from_html

                extracted = extract_from_html(html, url)
                content = extracted.get("content", "") or ""
                title = extracted.get("title", "") or title
                content_format = extracted.get("content_format", "text") or "text"

            snippet = content[:500] if content else ""

            return FetchResult(
                url=url,
                final_url=url,
                title=title,
                content=content,
                content_format=content_format,
                source=self.PROVIDER_NAME,
                snippet=snippet,
                raw={
                    "provider": "cloudflare_browser",
                    "account_id": self.account_id,
                },
            )
        except Exception as exc:
            # 异常封装，保证批量任务不被中断
            logger.warning("Cloudflare Browser fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "cloudflare_browser"},
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
            timeout: 每个 URL 超时秒数

        Returns:
            FetchResponse 聚合结果
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.fetch(u, timeout=timeout)

        results = await asyncio.gather(*[_fetch_one(u) for u in urls])
        result_list = list(results)
        ok = sum(1 for r in result_list if r.error is None)
        return FetchResponse(
            urls=urls,
            results=result_list,
            total=len(result_list),
            total_ok=ok,
            total_failed=len(result_list) - ok,
            provider=self.PROVIDER_NAME,
        )
