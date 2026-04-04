"""Bing 搜索引擎爬虫

通过 HTML 抓取 Bing 搜索结果页面。
Bing 对爬虫的检测相对宽松。

技术方案参考:
- ddgs 库 (deedy5) 的 Bing 集成
- Search-Engines-Scraper 的 Bing 模块

特点：
- 无需 API Key（爬虫方式）
- 反爬检测相对宽松
- 支持多语言搜索
- 微软搜索生态
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.bing")


class BingClient(BaseScraper):
    """Bing 搜索爬虫客户端
    
    Bing 反爬检测相对宽松，是 Google 的可靠替代。
    """

    ENGINE_NAME = "bing"
    BASE_URL = "https://www.bing.com/search"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Bing
        
        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        url = f"{self.BASE_URL}?q={quote_plus(query)}&count={min(max_results + 5, 50)}"
        
        resp = await self._fetch(url)
        html = resp.text
        
        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []
        
        # Bing 搜索结果容器
        # 主要选择器: li.b_algo (有机结果)
        for element in soup.select("li.b_algo"):
            # 标题在 h2 > a
            title_el = element.select_one("h2 a")
            if title_el is None:
                continue
            
            title = title_el.get_text(strip=True)
            raw_url = title_el.get("href", "")
            
            if not raw_url or not raw_url.startswith("http"):
                continue
            
            # Snippet: p 标签或 .b_caption p
            snippet = ""
            for sel in ["div.b_caption p", "p"]:
                snippet_el = element.select_one(sel)
                if snippet_el:
                    snippet = snippet_el.get_text(strip=True)
                    break
            
            if title and raw_url:
                results.append(WebSearchResult(
                    source=SourceType.WEB_BING,
                    title=title,
                    url=str(raw_url),
                    snippet=snippet,
                    engine=self.ENGINE_NAME,
                ))
                
            if len(results) >= max_results:
                break
        
        logger.info("Bing 返回 %d 条结果 (query=%s)", len(results), query)
        
        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_BING,
            results=results,
            total_results=len(results),
        )
