"""中文社区聚合搜索客户端

文件用途：
    聚合搜索多个中文技术/生活社区平台的内容，包括 linux.do、NodeSeek、
    HostLoc、V2EX、Coolapk（酷安）、小红书。

    通过对已有搜索引擎（DuckDuckGo）发起 site: 限定搜索实现，
    无需各平台 API Key 或登录凭证，纯只读检索。

    设计策略：
    - 对每个目标平台域名构造 `site:domain query` 搜索词
    - 通过 DuckDuckGo HTML 后端执行搜索
    - 聚合所有平台结果，标注来源平台标签
    - 按 URL 去重，保留首次出现的结果
    - 单平台查询失败不影响整体，记录警告后继续

函数/类清单：
    PLATFORM_DOMAINS（常量）
        - 功能：目标社区平台域名与显示标签的映射

    CommunityCnClient（类）
        - 功能：中文社区聚合搜索客户端
        - 继承：SouWenHttpClient
        - 关键属性：ENGINE_NAME = "community_cn"
        - 主要方法：search(query, max_results) -> WebSearchResponse
        - 辅助方法：
            _build_site_query(query, domain) -> str
            _label_snippet(snippet, platform_label) -> str

模块依赖：
    - asyncio: 并发执行多平台搜索
    - logging: 日志记录
    - souwen.models: str, WebSearchResult, WebSearchResponse
    - souwen.core.http_client: SouWenHttpClient
    - souwen.web.duckduckgo: DuckDuckGoClient（搜索后端）
"""

from __future__ import annotations

import asyncio
import logging

from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResult, WebSearchResponse

logger = logging.getLogger("souwen.web.community_cn")

# ── 目标社区平台域名 → 显示标签 ───────────────────────────
PLATFORM_DOMAINS: dict[str, str] = {
    "linux.do": "LinuxDo",
    "nodeseek.com": "NodeSeek",
    "hostloc.com": "HostLoc",
    "v2ex.com": "V2EX",
    "coolapk.com": "Coolapk",
    "xiaohongshu.com": "小红书",
}


def _build_site_query(query: str, domain: str) -> str:
    """构造 site: 限定搜索词

    Args:
        query: 用户原始查询
        domain: 目标网站域名

    Returns:
        带 site: 限定的搜索词，如 "site:v2ex.com Python 异步"
    """
    return f"site:{domain} {query}"


def _label_snippet(snippet: str, platform_label: str) -> str:
    """为 snippet 添加平台来源标签

    Args:
        snippet: 原始摘要文本
        platform_label: 平台显示名称

    Returns:
        带 [平台] 前缀的摘要文本
    """
    prefix = f"[{platform_label}] "
    if snippet.startswith(prefix):
        return snippet
    return f"{prefix}{snippet}"


class CommunityCnClient(SouWenHttpClient):
    """中文社区聚合搜索客户端

    通过 DuckDuckGo site: 搜索聚合多个中文社区平台内容。
    无需 API Key，零配置即可使用。支持的平台：
    linux.do、NodeSeek、HostLoc、V2EX、Coolapk、小红书。

    每个平台独立查询，单平台失败不影响其他平台结果。
    结果按 URL 去重，保留首次出现的条目。
    """

    ENGINE_NAME = "community_cn"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 延迟导入避免循环依赖，搜索时按需创建
        self._ddg_client: object | None = None

    def _get_ddg_client(self):
        """懒加载 DuckDuckGo 客户端实例"""
        if self._ddg_client is None:
            from souwen.web.duckduckgo import DuckDuckGoClient

            self._ddg_client = DuckDuckGoClient()
        return self._ddg_client

    async def close(self) -> None:
        """关闭自身及内部 DuckDuckGo 客户端的资源"""
        if self._ddg_client is not None:
            await self._ddg_client.close()
            self._ddg_client = None
        await super().close()

    async def _search_one_platform(
        self,
        query: str,
        domain: str,
        label: str,
        per_platform_limit: int,
    ) -> list[WebSearchResult]:
        """搜索单个平台

        Args:
            query: 用户原始查询
            domain: 平台域名
            label: 平台显示标签
            per_platform_limit: 该平台最大返回条数

        Returns:
            该平台的搜索结果列表（可能为空）
        """
        site_query = _build_site_query(query, domain)
        try:
            ddg = self._get_ddg_client()
            resp = await ddg.search(
                site_query,
                max_results=per_platform_limit,
                max_pages=1,
            )
            results: list[WebSearchResult] = []
            for item in resp.results:
                results.append(
                    WebSearchResult(
                        source="community_cn",
                        title=item.title,
                        url=item.url,
                        snippet=_label_snippet(item.snippet, label),
                        engine=f"community_cn:{domain}",
                        raw=item.raw,
                    )
                )
            return results
        except Exception:
            logger.warning("社区搜索失败 [%s] query=%r", domain, query, exc_info=True)
            return []

    async def search(
        self,
        query: str,
        max_results: int = 20,
    ) -> WebSearchResponse:
        """聚合搜索多个中文社区平台

        对每个目标平台并发执行 site: 限定搜索，聚合结果并去重。
        单平台查询失败会记录警告但不影响整体。

        Args:
            query: 搜索关键词
            max_results: 最大返回结果总数（默认 20）

        Returns:
            WebSearchResponse 包含聚合后的搜索结果
        """
        per_platform = max(2, (max_results + len(PLATFORM_DOMAINS) - 1) // len(PLATFORM_DOMAINS))

        tasks = [
            self._search_one_platform(query, domain, label, per_platform)
            for domain, label in PLATFORM_DOMAINS.items()
        ]

        platform_results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_urls: set[str] = set()
        merged: list[WebSearchResult] = []

        for result in platform_results:
            if isinstance(result, BaseException):
                logger.warning("平台搜索任务异常: %s", result)
                continue
            for item in result:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                merged.append(item)

        merged = merged[:max_results]

        return WebSearchResponse(
            query=query,
            source="community_cn",
            total_results=len(merged),
            results=merged,
        )
