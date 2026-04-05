"""Mojeek 搜索引擎

Mojeek 是一个独立的英国搜索引擎，拥有自己的搜索索引。
URL: https://www.mojeek.com/search?q=...

特点：
- 无需 API Key
- 独立搜索索引（非 Google/Bing 代理）
- 英国公司，注重隐私
- 不追踪用户，不使用第三方索引
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.mojeek")


class MojeekClient(BaseScraper):
    """Mojeek 搜索客户端

    Mojeek 是英国独立搜索引擎，拥有自己的爬虫和索引。
    通过 CSS 选择器解析搜索结果。
    """

    ENGINE_NAME = "mojeek"
    BASE_URL = "https://www.mojeek.com/search"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Mojeek

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

        try:
            for element in soup.select("ul.results-standard > li"):
                # 提取标题和链接
                title_el = element.select_one("a.title")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)
                raw_url = title_el.get("href", "")

                # 提取 snippet
                snippet_el = element.select_one("p.s")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                if not raw_url or not raw_url.startswith(("http://", "https://")):
                    continue

                if title:
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_MOJEEK,
                            title=title,
                            url=str(raw_url),
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Mojeek HTML 解析失败: %s", e)

        logger.info("Mojeek 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_MOJEEK,
            results=results,
            total_results=len(results),
        )
