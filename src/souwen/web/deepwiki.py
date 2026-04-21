"""DeepWiki 文档抓取客户端

文件用途：
    抓取 deepwiki.com 上的 GitHub 仓库 AI 文档，将其转换为 Markdown。
    DeepWiki（https://deepwiki.com）为 GitHub 仓库自动生成结构化 Wiki。

    核心设计参照：
        https://github.com/regenrek/deepwiki-mcp（MIT License）
    本模块使用 SouWen 已有基础设施（httpx / site_crawler / jina_reader）在
    Python 中复现其能力，不直接依赖 MCP 协议，融入 SouWen 统一数据模型。

函数/类清单：
    resolve_github_repo(keyword, github_token=None) -> str
        - 功能：通过 GitHub Search API 将库名解析为 "owner/repo" 格式
        - 参照 deepwiki-mcp resolveRepoFetch.ts
        - 输入：keyword 关键词（库名或 owner/repo）
        - 输出："owner/repo" 字符串
        - 异常：ValueError（无匹配或请求失败）

    _parse_deepwiki_url(url_or_shorthand) -> str
        - 功能：将多种格式归一化为完整的 deepwiki.com URL
        - 支持格式：
            * 完整 URL: https://deepwiki.com/owner/repo
            * owner/repo: shadcn-ui/ui
            * 单词（库名）: tailwind
        - 输出：https://deepwiki.com/owner/repo

    DeepWikiClient（类）
        - 功能：DeepWiki 文档抓取客户端
        - 关键属性：PROVIDER_NAME = "deepwiki"
        - 主要方法：
            * fetch(url_or_shorthand, max_depth, mode, timeout) → FetchResult
            * fetch_batch(urls, ...) → FetchResponse

模块依赖：
    - asyncio: 异步执行
    - logging: 日志记录
    - re: URL 格式判断
    - httpx: GitHub API 请求
    - souwen.config: 读取 github_token
    - souwen.models: FetchResult, FetchResponse
    - souwen.web.site_crawler: SiteCrawlerClient（BFS 爬取）
    - souwen.web.jina_reader: JinaReaderClient（代理回退）

技术要点：
    - 域安全：只允许 deepwiki.com 域
    - 输入归一化：完整 URL / owner/repo 简写 / 单词关键词 均可使用
    - 库名解析：通过 GitHub Search API 解析单词关键词（对齐 resolveRepoFetch.ts）
    - 主策略：site_crawler 直接爬取（BFS，深度可配置）
    - 回退策略：jina_reader（https://r.jina.ai/https://deepwiki.com/...）
    - 两种输出模式：aggregate（单文档）/ pages（分页）
    - 空内容保护：两种策略均失败时返回包含 error 的 FetchResult
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Literal
from urllib.parse import urlparse

import httpx

from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.deepwiki")

_DEEPWIKI_DOMAIN = "deepwiki.com"
_DEEPWIKI_BASE = "https://deepwiki.com"
_GITHUB_API = "https://api.github.com"
_USER_AGENT = "SouWen-DeepWiki/1.0 (+https://github.com/BlueSkyXN/SouWen)"


async def resolve_github_repo(
    keyword: str,
    github_token: str | None = None,
) -> str:
    """通过 GitHub Search API 将库名关键词解析为 "owner/repo"

    参照 deepwiki-mcp 的 resolveRepoFetch.ts 实现。SouWen 已有 GitHubClient，
    此处直接使用 httpx 避免循环依赖，与 GitHubClient 行为保持一致。

    Args:
        keyword: 库名或搜索词（如 "tailwind"、"shadcn"）
        github_token: GitHub Personal Access Token（可选，提高速率限制）

    Returns:
        "owner/repo" 格式字符串

    Raises:
        ValueError: GitHub 请求失败或没有匹配仓库
    """
    # 若已是 owner/repo 格式，直接返回
    if re.match(r"^[^/\s]+/[^/\s]+$", keyword.strip()):
        return keyword.strip()

    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": _USER_AGENT,
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    params = {"q": f"{keyword} in:name", "per_page": 1}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_GITHUB_API}/search/repositories",
                params=params,
                headers=headers,
            )
    except Exception as exc:
        raise ValueError(f"GitHub API 请求失败: {exc}") from exc

    if not resp.is_success:
        raise ValueError(f"GitHub API 返回错误状态: {resp.status_code}")

    data = resp.json()
    items = data.get("items") or []
    if not items:
        raise ValueError(f"GitHub 未找到匹配 '{keyword}' 的仓库")

    full_name: str = items[0].get("full_name", "")
    if not full_name:
        raise ValueError("GitHub API 响应缺少 full_name 字段")

    logger.debug("GitHub 库名解析: %s → %s", keyword, full_name)
    return full_name


async def _parse_deepwiki_url(url_or_shorthand: str, github_token: str | None = None) -> str:
    """将多种格式归一化为完整 deepwiki.com URL

    支持的输入格式（参照 deepwiki-mcp deepwiki.ts 的归一化逻辑）：
    - 完整 URL：https://deepwiki.com/owner/repo[/page]  → 原样返回
    - owner/repo 简写：shadcn-ui/ui  → https://deepwiki.com/shadcn-ui/ui
    - 单词关键词：tailwind           → 解析 GitHub → https://deepwiki.com/owner/repo

    Args:
        url_or_shorthand: 目标 URL 或简写
        github_token: GitHub Token（关键词解析时使用）

    Returns:
        完整的 deepwiki.com URL

    Raises:
        ValueError: 域名不是 deepwiki.com，或关键词解析失败
    """
    text = url_or_shorthand.strip()

    # 已是完整 URL
    if re.match(r"^https?://", text):
        parsed = urlparse(text)
        if parsed.hostname != _DEEPWIKI_DOMAIN:
            raise ValueError(f"域名安全检查失败：仅允许 {_DEEPWIKI_DOMAIN}，收到 {parsed.hostname}")
        return text

    # owner/repo 格式（含可选子路径）
    if re.match(r"^[^/\s]+/[^/\s]+", text):
        return f"{_DEEPWIKI_BASE}/{text}"

    # 单词关键词：通过 GitHub API 解析
    full_name = await resolve_github_repo(text, github_token=github_token)
    return f"{_DEEPWIKI_BASE}/{full_name}"


class DeepWikiClient:
    """DeepWiki 文档抓取客户端

    获取 deepwiki.com 上某 GitHub 仓库的 AI 生成文档，输出 Markdown。
    核心实现参照 deepwiki-mcp（https://github.com/regenrek/deepwiki-mcp），
    使用 SouWen 的 site_crawler（BFS）+ jina_reader 回退策略替代原 TypeScript 实现。

    Args:
        github_token: GitHub Token（用于关键词解析，可选）
        jina_api_key: Jina Reader API Key（回退策略，可选）
        prefer_jina: 优先使用 Jina Reader（默认 False，优先 site_crawler）
    """

    PROVIDER_NAME = "deepwiki"

    def __init__(
        self,
        github_token: str | None = None,
        jina_api_key: str | None = None,
        prefer_jina: bool = False,
    ) -> None:
        # 自动从 SouWen 配置读取 Token（若未显式提供）
        if github_token is None or jina_api_key is None:
            try:
                from souwen.config import get_config

                cfg = get_config()
                if github_token is None:
                    github_token = getattr(cfg, "github_token", None) or None
                if jina_api_key is None:
                    jina_api_key = getattr(cfg, "jina_api_key", None) or None
            except Exception:
                pass

        self._github_token = github_token
        self._jina_api_key = jina_api_key
        self._prefer_jina = prefer_jina

    async def fetch(
        self,
        url_or_shorthand: str,
        max_depth: int = 1,
        mode: Literal["aggregate", "pages"] = "aggregate",
        timeout: float = 60.0,
    ) -> FetchResult:
        """抓取指定仓库的 DeepWiki 文档

        Args:
            url_or_shorthand: deepwiki.com URL 或 owner/repo 或库名关键词
            max_depth: 爬取深度（0 = 仅首页，1 = 首页 + 子页面，对齐 deepwiki-mcp 默认值）
            mode: 输出模式（aggregate / pages）
            timeout: 请求超时秒数

        Returns:
            FetchResult（aggregate 模式为单条聚合，pages 模式见 fetch_pages）
        """
        # 归一化 URL
        try:
            url = await _parse_deepwiki_url(url_or_shorthand, github_token=self._github_token)
        except ValueError as exc:
            return FetchResult(
                url=url_or_shorthand,
                final_url=url_or_shorthand,
                source=self.PROVIDER_NAME,
                error=str(exc),
            )

        logger.info("DeepWiki 抓取: url=%s max_depth=%d mode=%s", url, max_depth, mode)

        # 主策略：site_crawler BFS
        if not self._prefer_jina:
            result = await self._fetch_with_site_crawler(url, max_depth, mode, timeout)
            if result and result.content.strip():
                return result

        # 回退策略 1：Jina Reader（cloud Markdown 提取，可绕过 JS 渲染）
        jina_result = await self._fetch_with_jina(url, timeout)
        if jina_result and jina_result.content.strip():
            return jina_result

        # 回退策略 2：若 prefer_jina 优先但失败，再试 site_crawler
        if self._prefer_jina:
            result = await self._fetch_with_site_crawler(url, max_depth, mode, timeout)
            if result and result.content.strip():
                return result

        # 全部失败
        return FetchResult(
            url=url,
            final_url=url,
            source=self.PROVIDER_NAME,
            error="DeepWiki 抓取失败：site_crawler 与 jina_reader 均返回空内容",
            raw={"provider": self.PROVIDER_NAME, "url": url},
        )

    async def _fetch_with_site_crawler(
        self,
        url: str,
        max_depth: int,
        mode: Literal["aggregate", "pages"],
        timeout: float,
    ) -> FetchResult | None:
        """使用 SiteCrawlerClient 爬取 DeepWiki 页面（主策略）"""
        try:
            from souwen.web.site_crawler import SiteCrawlerClient

            async with SiteCrawlerClient(respect_robots_txt=True) as crawler:
                resp = await crawler.crawl(
                    url,
                    max_depth=max_depth,
                    max_concurrency=5,
                    timeout=timeout,
                    mode=mode,
                    allowed_domain=_DEEPWIKI_DOMAIN,
                )

            if not resp.results:
                return None

            # aggregate 模式：取唯一聚合结果
            ok_results = [r for r in resp.results if not r.error]
            if not ok_results:
                return None

            if mode == "aggregate":
                result = ok_results[0]
                # 更新 source 标识
                return FetchResult(
                    url=url,
                    final_url=result.final_url,
                    title=result.title,
                    content=result.content,
                    content_format=result.content_format,
                    source=self.PROVIDER_NAME,
                    snippet=result.content[:500],
                    raw={
                        **result.raw,
                        "strategy": "site_crawler",
                        "deepwiki_url": url,
                    },
                )
            else:
                # pages 模式：将多页聚合后返回单个 FetchResult
                parts = [f"# {r.title}\n\n{r.content}" for r in ok_results]
                combined = "\n\n---\n\n".join(parts)
                return FetchResult(
                    url=url,
                    final_url=url,
                    title=url,
                    content=combined,
                    content_format="markdown",
                    source=self.PROVIDER_NAME,
                    snippet=combined[:500],
                    raw={
                        "strategy": "site_crawler",
                        "deepwiki_url": url,
                        "total_pages": len(ok_results),
                    },
                )
        except Exception as exc:
            logger.debug("site_crawler 策略失败: url=%s err=%s", url, exc)
            return None

    async def _fetch_with_jina(
        self,
        url: str,
        timeout: float,
    ) -> FetchResult | None:
        """使用 Jina Reader 代理抓取（回退策略）"""
        try:
            from souwen.web.jina_reader import JinaReaderClient

            async with JinaReaderClient(api_key=self._jina_api_key) as client:
                result = await client.fetch(url, timeout=timeout)

            if result.error:
                logger.debug("jina_reader 策略失败: url=%s err=%s", url, result.error)
                return None

            return FetchResult(
                url=url,
                final_url=result.final_url,
                title=result.title,
                content=result.content,
                content_format=result.content_format,
                source=self.PROVIDER_NAME,
                snippet=result.content[:500],
                raw={
                    **result.raw,
                    "strategy": "jina_reader",
                    "deepwiki_url": url,
                },
            )
        except Exception as exc:
            logger.debug("jina_reader 策略失败: url=%s err=%s", url, exc)
            return None

    async def fetch_batch(
        self,
        urls: list[str],
        max_depth: int = 1,
        mode: Literal["aggregate", "pages"] = "aggregate",
        timeout: float = 60.0,
        max_concurrency: int = 3,
    ) -> FetchResponse:
        """批量抓取多个 DeepWiki 仓库文档

        Args:
            urls: deepwiki.com URL / owner/repo / 关键词列表
            max_depth: 爬取深度
            mode: 输出模式
            timeout: 超时秒数
            max_concurrency: 最大并发仓库数

        Returns:
            FetchResponse
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.fetch(u, max_depth=max_depth, mode=mode, timeout=timeout)

        results = await asyncio.gather(*[fetch_one(u) for u in urls])
        result_list = list(results)
        ok_count = sum(1 for r in result_list if not r.error)
        fail_count = sum(1 for r in result_list if r.error)

        return FetchResponse(
            urls=urls,
            results=result_list,
            total=len(result_list),
            total_ok=ok_count,
            total_failed=fail_count,
            provider=self.PROVIDER_NAME,
            meta={"max_depth": max_depth, "mode": mode},
        )

    async def __aenter__(self) -> "DeepWikiClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass
