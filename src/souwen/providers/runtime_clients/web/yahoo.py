"""Yahoo 搜索引擎爬虫"""

from __future__ import annotations

import logging
from urllib.parse import unquote, quote_plus

from bs4 import BeautifulSoup

from souwen.providers.runtime_clients.models import WebSearchResult, WebSearchResponse
from souwen.common_runtime.provider_support.scraper.base import BaseScraper

logger = logging.getLogger("souwen.providers.runtime_clients.web.yahoo")


class YahooClient(BaseScraper):
    """Yahoo 搜索客户端

    Yahoo 搜索由 Bing 提供支持。
    对数据中心 IP 较为宽容（相比其他引擎）。
    """

    ENGINE_NAME = "yahoo"
    BASE_URL = "https://search.yahoo.com/search"

    def __init__(self, **kwargs):
        # 初始化爬虫配置：最小延迟 1.5s、最大延迟 4.0s、最多重试 3 次
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Yahoo

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # 构建搜索 URL（p 参数为查询关键词）
        url = f"{self._resolved_base_url}?p={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # 遍历 Yahoo 搜索结果容器（.algo 类选择器）
            for element in soup.select(".algo"):
                title_el = element.select_one("h3")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)

                # 提取链接
                link_el = element.select_one(".compTitle a")
                raw_url = link_el.get("href", "") if link_el else ""

                # 提取 snippet
                snippet_el = element.select_one(".compText")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                # Yahoo URL 重定向解码（格式: .../RU=ENCODED_URL/RK=.../RS=...）
                real_url = self._decode_yahoo_url(str(raw_url))

                if not real_url or not real_url.startswith(("http://", "https://")):
                    continue

                if title:
                    results.append(
                        WebSearchResult(
                            source="yahoo",
                            title=title,
                            url=real_url,
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Yahoo HTML 解析失败: %s", e)

        logger.info("Yahoo 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="yahoo",
            results=results,
            total_results=len(results),
        )

    @staticmethod
    def _decode_yahoo_url(url: str) -> str:
        """解码 Yahoo 重定向 URL

        Yahoo 重定向格式: .../RU=ENCODED_URL/RK=.../RS=...
        提取 RU= 和 /RK= 之间的内容并 URL 解码。
        """
        if "RU=" in url and "/RK=" in url:
            start = url.find("RU=") + 3
            sub = url[start:]
            end = sub.find("/RK=")
            if end != -1:
                try:
                    return unquote(sub[:end])
                except (ValueError, UnicodeDecodeError):
                    pass
        return url
