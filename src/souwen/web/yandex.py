"""Client for Yandex

Purpose:
    Yandex search results via web scraping

API Endpoint:
    Yandex service

Key Features:
    - Russian search engine, scrapes search results

Engine Class:
    YandexClient(SouWenHttpClient)
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

logger = logging.getLogger("souwen.web.yandex")


class YandexClient(BaseScraper):
    """Yandex 搜索客户端

    Yandex 是俄罗斯搜索引擎，拥有独立索引。
    反爬虫机制较强，使用较长的请求延迟。
    通过 CSS 选择器解析搜索结果。
    """

    ENGINE_NAME = "yandex"
    BASE_URL = "https://yandex.com/search/"

    def __init__(self, **kwargs):
        # Yandex 反爬虫较强，使用较长延迟
        super().__init__(min_delay=2.0, max_delay=5.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Yandex

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        url = f"{self.BASE_URL}?text={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            for element in soup.select("li.serp-item, .OrganicResult"):
                # 尝试多个选择器提取标题和链接
                title_el = element.select_one("a.OrganicTitle-Link") or element.select_one(
                    ".organic__url"
                )
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)
                raw_url = title_el.get("href", "")

                # 提取 snippet，尝试多个选择器
                snippet_el = element.select_one(".OrganicTextContentSpan") or element.select_one(
                    ".TextContainer"
                )
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                if not raw_url or not raw_url.startswith(("http://", "https://")):
                    continue

                if title:
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_YANDEX,
                            title=title,
                            url=str(raw_url),
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Yandex HTML 解析失败: %s", e)

        logger.info("Yandex 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_YANDEX,
            results=results,
            total_results=len(results),
        )
