"""Google 搜索引擎爬虫

通过 HTML 抓取 Google 搜索结果页面。
高风险但高价值 — Google 积极对抗爬虫。

技术方案参考:
- googlesearch-python: requests + BS4
- Search-Engines-Scraper: CSS 选择器解析
- Whoogle: Google 无 JS 版本

特点：
- 无需 API Key（爬虫方式）
- 使用 TLS 指纹模拟绕过 JA3 检测
- Google 可能随时更改页面结构
- 建议搭配代理使用
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.google")


class GoogleClient(BaseScraper):
    """Google 搜索爬虫客户端

    注意：Google 反爬能力极强，建议：
    1. 使用 curl_cffi TLS 指纹模拟
    2. 搭配代理池使用
    3. 控制请求频率（默认 min_delay=3s）
    """

    ENGINE_NAME = "google"
    BASE_URL = "https://www.google.com/search"

    def __init__(self, **kwargs):
        # Google 需要更长的请求间隔
        super().__init__(min_delay=3.0, max_delay=7.0, max_retries=2, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Google

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数
        """
        params = {
            "q": query,
            "num": str(min(max_results + 5, 100)),  # 多请求一些以弥补过滤
            "hl": "en",
        }
        url = f"{self.BASE_URL}?q={quote_plus(query)}&num={params['num']}&hl=en"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # Google 搜索结果的主要容器选择器
            # 方法1: div.g 是经典的结果容器
            for element in soup.select("div.g"):
                # 提取标题和链接
                title_el = element.select_one("h3")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)

                # 链接通常在 h3 的父级 a 标签或 div.g 内的第一个 a 标签
                link_el = element.select_one("a[href]")
                if link_el is None:
                    continue
                raw_url = link_el.get("href", "")

                # Google URL 解码：/url?q=REAL_URL&sa=... 或直接 URL
                real_url = self._decode_google_url(str(raw_url))
                if not real_url or real_url.startswith("/"):
                    continue

                # 提取 snippet（多种可能的选择器）
                snippet = ""
                for sel in [
                    "div.VwiC3b",  # 当前常见
                    "span.aCOpRe",  # 旧版
                    "div[data-sncf]",  # 替代
                    "div.IsZvec",  # 另一种
                ]:
                    snippet_el = element.select_one(sel)
                    if snippet_el:
                        snippet = snippet_el.get_text(strip=True)
                        break

                if title and real_url:
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_GOOGLE,
                            title=title,
                            url=real_url,
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Google HTML 解析失败: %s", e)

        logger.info("Google 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_GOOGLE,
            results=results,
            total_results=len(results),
        )

    @staticmethod
    def _decode_google_url(url: str) -> str:
        """解码 Google 重定向 URL

        Google 有多种 URL 格式:
        1. /url?q=REAL_URL&sa=... (重定向)
        2. 直接 URL (https://example.com)
        3. /search?... (内部链接，过滤)
        """
        if url.startswith("/url?"):
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            q_values = qs.get("q", [])
            if q_values and q_values[0]:
                return unquote(q_values[0])
        if url.startswith("http"):
            return url
        return ""
