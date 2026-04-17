"""Client for Startpage

Purpose:
    Privacy-preserving search results

API Endpoint:
    Startpage service

Key Features:
    - Anonymous search, returns encrypted results from Google

Engine Class:
    StartpageClient(SouWenHttpClient)
        async def search(query, max_results) -> WebSearchResponse

Returns:
    WebSearchResponse with title, url, snippet fields
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.startpage")


class StartpageClient(BaseScraper):
    """Startpage 搜索客户端

    Startpage 使用 Google 搜索结果，但不追踪用户。
    通过 CSS 选择器解析搜索结果。
    """

    ENGINE_NAME = "startpage"
    BASE_URL = "https://www.startpage.com/sp/search"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Startpage

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        url = f"{self.BASE_URL}?query={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            for element in soup.select(".w-gl__result"):
                title_el = element.select_one(".w-gl__result-title")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)

                # 提取链接
                link_el = element.select_one("a.w-gl__result-title")
                raw_url = link_el.get("href", "") if link_el else ""

                # 提取 snippet
                snippet_el = element.select_one(".w-gl__description")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                if not raw_url or not raw_url.startswith(("http://", "https://")):
                    continue

                if title:
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_STARTPAGE,
                            title=title,
                            url=str(raw_url),
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Startpage HTML 解析失败: %s", e)

        logger.info("Startpage 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_STARTPAGE,
            results=results,
            total_results=len(results),
        )
