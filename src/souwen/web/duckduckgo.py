"""DuckDuckGo HTML 搜索引擎

移植自 SoSearch/src/engines/duckduckgo.rs
使用 DuckDuckGo 的轻量 HTML 版本（html.duckduckgo.com），
避免 JavaScript 渲染依赖。

特点：
- 无需 API Key
- 使用 HTML 版本，无需 JS 渲染
- 通过 uddg= 重定向参数提取真实 URL
"""

from __future__ import annotations

import logging
from urllib.parse import unquote, quote_plus

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.duckduckgo")


class DuckDuckGoClient(BaseScraper):
    """DuckDuckGo HTML 搜索客户端

    使用 html.duckduckgo.com 轻量版本，无需 JavaScript 渲染。
    通过 CSS 选择器解析搜索结果。
    """

    ENGINE_NAME = "duckduckgo"
    BASE_URL = "https://html.duckduckgo.com/html/"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 DuckDuckGo

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

        for element in soup.select(".result"):
            title_el = element.select_one(".result__a")
            if title_el is None:
                continue

            title = title_el.get_text(strip=True)
            raw_url = title_el.get("href", "")

            # 提取 snippet
            snippet_el = element.select_one(".result__snippet")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            # DuckDuckGo URL 重定向解码
            # 格式: //duckduckgo.com/l/?uddg=ENCODED_URL&rut=...
            real_url = self._decode_ddg_url(str(raw_url))

            if title and real_url:
                results.append(
                    WebSearchResult(
                        source=SourceType.WEB_DUCKDUCKGO,
                        title=title,
                        url=real_url,
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )

            if len(results) >= max_results:
                break

        logger.info("DuckDuckGo 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_DUCKDUCKGO,
            results=results,
            total_results=len(results),
        )

    @staticmethod
    def _decode_ddg_url(url: str) -> str:
        """解码 DuckDuckGo 重定向 URL

        DuckDuckGo 通过 //duckduckgo.com/l/?uddg=ENCODED_URL 跳转。
        提取真实 URL 并解码。
        """
        if url.startswith("//duckduckgo.com/l/?uddg="):
            # 提取 uddg= 之后的部分
            parts = url.split("uddg=", 1)
            if len(parts) > 1:
                encoded = parts[1].split("&", 1)[0]
                return unquote(encoded)
        return url
