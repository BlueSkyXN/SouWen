"""Brave 搜索引擎

移植自 SoSearch/src/engines/brave.rs
Brave Search 拥有独立的搜索索引（非 Bing/Google 驱动）。

特点：
- 无需 API Key
- 独立索引，结果与 Google/Bing 不同
- 隐私友好
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.brave")


class BraveClient(BaseScraper):
    """Brave 搜索客户端

    Brave Search 拥有独立索引（非 Bing/Google 驱动），
    提供差异化搜索结果。
    """

    ENGINE_NAME = "brave"
    BASE_URL = "https://search.brave.com/search"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Brave

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        url = f"{self.BASE_URL}?q={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        for element in soup.select(".snippet"):
            title_el = element.select_one(".title")
            if title_el is None:
                continue

            title = title_el.get_text(strip=True)

            # 提取第一个链接
            link_el = element.select_one("a")
            raw_url = link_el.get("href", "") if link_el else ""

            # 提取 snippet（多个可能的选择器）
            snippet = ""
            for selector in [".snippet-description", ".snippet-content", ".description"]:
                snippet_el = element.select_one(selector)
                if snippet_el:
                    snippet = snippet_el.get_text(strip=True)
                    break

            # 过滤内部链接
            if raw_url and not raw_url.startswith("/") and title:
                results.append(
                    WebSearchResult(
                        source=SourceType.WEB_BRAVE,
                        title=title,
                        url=str(raw_url),
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )

            if len(results) >= max_results:
                break

        logger.info("Brave 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_BRAVE,
            results=results,
            total_results=len(results),
        )
