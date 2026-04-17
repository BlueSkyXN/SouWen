"""Bing 搜索引擎爬虫

文件用途：
    Bing 搜索引擎爬虫客户端。Bing 对爬虫的反爬检测相对宽松，
    是 Google 的可靠替代。通过 HTML 抓取获取搜索结果。

函数/类清单：
    BingClient（类）
        - 功能：Bing 搜索爬虫客户端，通过 HTML 解析获取搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "bing", BASE_URL = "https://www.bing.com/search",
                  min_delay = 1.5, max_delay = 4.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    BingClient.__init__(**kwargs)
        - 功能：初始化 Bing 搜索客户端
        - 输入：**kwargs 传递给 BaseScraper 的参数
        - 输出：实例

    BingClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询 Bing 搜索，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码
    - bs4: HTML 解析
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型
    - souwen.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 CSS 选择器 li.b_algo 定位搜索结果容器
    - 标题在 h2 > a，snippet 在 div.b_caption p 或 p
    - URL 必须是 http 开头（过滤相对路径）
    - 支持多个选择器降级策略
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
        # 初始化爬虫配置：最小延迟 1.5s、最大延迟 4.0s、最多重试 3 次
        super().__init__(min_delay=1.5, max_delay=4.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Bing

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # URL 参数：q 搜索词，count 结果数（预留余量以应对过滤）
        url = f"{self.BASE_URL}?q={quote_plus(query)}&count={min(max_results + 5, 50)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # Bing 搜索结果容器：li.b_algo （有机结果）
            for element in soup.select("li.b_algo"):
                # 标题在 h2 > a
                title_el = element.select_one("h2 a")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)
                raw_url = title_el.get("href", "")

                # 过滤非 HTTP 链接（相对路径等无效）
                if not raw_url or not raw_url.startswith("http"):
                    continue

                # Snippet 提取：尝试 div.b_caption p，再尝试 p
                snippet = ""
                for sel in ["div.b_caption p", "p"]:
                    snippet_el = element.select_one(sel)
                    if snippet_el:
                        snippet = snippet_el.get_text(strip=True)
                        break

                if title and raw_url:
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_BING,
                            title=title,
                            url=str(raw_url),
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Bing HTML 解析失败: %s", e)

        logger.info("Bing 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_BING,
            results=results,
            total_results=len(results),
        )
