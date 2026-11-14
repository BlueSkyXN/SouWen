"""brave（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
from bs4 import BeautifulSoup
from collections.abc import Mapping
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.common_runtime.provider_support.scraper.base import BaseScraper
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import HttpOperation, client_scraper_spec, ScraperSearchProvider
from souwen.providers.runtime_clients.models import WebSearchResult, WebSearchResponse
from typing import Any
from urllib.parse import quote_plus


from souwen.platform.provider_spec import scraper_search_manifest

BRAVE_PROVIDER_MANIFEST = scraper_search_manifest(
    "brave",
    "BraveSearchProvider",
    ["search.brave.com"],
    max_egress="browser",
)


BRAVE_PROVIDER_SPEC = client_scraper_spec(
    "brave", "web", "search.brave.com", "html", (HttpOperation(method="GET", endpoint="/search"),)
)


logger = logging.getLogger("souwen.providers.runtime_clients.web.brave")


class BraveClient(BaseScraper):
    """Brave 搜索客户端

    Brave Search 拥有独立索引（非 Bing/Google 驱动），
    提供差异化搜索结果。
    """

    ENGINE_NAME = "brave"
    BASE_URL = "https://search.brave.com/search"

    def __init__(self, **kwargs):
        # 初始化爬虫配置：最小延迟 1.5s、最大延迟 4.0s、最多重试 3 次
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Brave

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        url = f"{self._resolved_base_url}?q={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # 遍历 Brave 搜索结果的容器 .snippet
            for element in soup.select(".snippet"):
                # 标题在 .title
                title_el = element.select_one(".title")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)

                # 提取第一个链接（a 标签的 href）
                link_el = element.select_one("a")
                raw_url = link_el.get("href", "") if link_el else ""

                # 提取 snippet（描述文本），多个可能的选择器
                snippet = ""
                for selector in [".snippet-description", ".snippet-content", ".description"]:
                    snippet_el = element.select_one(selector)
                    if snippet_el:
                        snippet = snippet_el.get_text(strip=True)
                        break

                # 过滤内部链接（/ 开头的相对路径）
                if raw_url and not raw_url.startswith("/") and title:
                    results.append(
                        WebSearchResult(
                            source="brave",
                            title=title,
                            url=str(raw_url),
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Brave HTML 解析失败: %s", e)

        logger.info("Brave 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="brave",
            results=results,
            total_results=len(results),
        )


class BraveSearchProvider(ScraperSearchProvider):
    def __init__(self, client, *, enabled: bool = True):
        super().__init__(client, provider_id="brave", domain="web", enabled=enabled)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = BraveClient(follow_redirects=False)
    return BraveSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = BRAVE_PROVIDER_MANIFEST
SPEC = BRAVE_PROVIDER_SPEC
PROVIDER_TYPE = BraveSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
