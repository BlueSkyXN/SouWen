"""Google 搜索引擎爬虫

文件用途：
    Google 搜索引擎爬虫客户端。高风险但高价值 —— Google 积极对抗爬虫，
    需配合 TLS 指纹模拟和代理池使用。通过 HTML 解析获取搜索结果。

函数/类清单：
    GoogleClient（类）
        - 功能：Google 搜索爬虫客户端，通过 HTML 解析获取搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "google", BASE_URL = "https://www.google.com/search",
                  min_delay = 3.0, max_delay = 7.0, max_retries = 2（更严格的配置）
        - 主要方法：search(query, max_results) -> WebSearchResponse

    GoogleClient.__init__(**kwargs)
        - 功能：初始化 Google 搜索客户端（需要更长的请求间隔）
        - 输入：**kwargs 传递给 BaseScraper 的参数
        - 输出：实例

    GoogleClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询 Google，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

    GoogleClient._decode_google_url(url) -> str
        - 功能：解码 Google 重定向 URL（从 /url?q= 参数提取真实 URL）
        - 输入：url Google 格式的 URL 字符串
        - 输出：解码后的真实 URL；内部链接返回空字符串

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码/解码、查询参数解析
    - bs4: HTML 解析
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型
    - souwen.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - Google 反爬能力极强，建议配合 curl_cffi TLS 指纹模拟、代理池使用
    - CSS 选择器：div.g（结果容器）、h3（标题）、a（链接）
    - 解码 Google URL：/url?q=REAL_URL&sa=... 或直接 URL
    - Snippet 多种选择器：VwiC3b、aCOpRe、data-sncf、IsZvec
    - num 参数预留余量以应对过滤
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
        # Google 需要更长的请求间隔（反爬严格）
        # min_delay=3.0s、max_delay=7.0s、最多重试 2 次（比其他引擎严格）
        super().__init__(min_delay=3.0, max_delay=7.0, max_retries=2, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Google

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # num 多请求一些（+5）以弥补过滤和重定向导致的结果减少
        params = {
            "q": query,
            "num": str(min(max_results + 5, 100)),  # 预留余量
            "hl": "en",
        }
        url = f"{self.BASE_URL}?q={quote_plus(query)}&num={params['num']}&hl=en"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # Google 搜索结果的主要容器：div.g
            for element in soup.select("div.g"):
                # 提取标题：h3 标签
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
                # 过滤相对路径和内部链接
                if not real_url or real_url.startswith("/"):
                    continue

                # 提取 snippet（多种可能的 CSS 类名，因为 Google 经常改）
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

        Args:
            url: Google 格式的 URL 字符串

        Returns:
            str: 解码后的真实 URL；内部链接或无效返回空字符串
        """
        if url.startswith("/url?"):
            # 解析查询参数，提取 q 的值
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            q_values = qs.get("q", [])
            if q_values and q_values[0]:
                # URL 解码恢复真实链接
                return unquote(q_values[0])
        # 直接 HTTP/HTTPS URL
        if url.startswith("http"):
            return url
        # 其他情况（相对路径、内部链接等）返回空字符串
        return ""
