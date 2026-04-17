"""Brave 搜索引擎

文件用途：
    Brave Search 搜索引擎爬虫客户端。Brave Search 拥有独立的搜索索引
    （非 Bing/Google 驱动），隐私友好，无需 API Key。

函数/类清单：
    BraveClient（类）
        - 功能：Brave 搜索爬虫客户端，通过 HTML 解析获取搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "brave", BASE_URL = "https://search.brave.com/search",
                  min_delay = 1.5, max_delay = 4.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    BraveClient.__init__(**kwargs)
        - 功能：初始化 Brave 搜索客户端
        - 输入：**kwargs 传递给 BaseScraper 的参数
        - 输出：实例

    BraveClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询 Brave 搜索，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码
    - bs4: HTML 解析
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型
    - souwen.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 CSS 选择器 .snippet 定位搜索结果容器
    - 标题在 .title，链接在 a 标签的 href
    - 过滤相对路径链接（/ 开头）
    - Snippet 多个选择器降级策略
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
        # 初始化爬虫配置：最小延迟 1.5s、最大延迟 4.0s、最多重试 3 次
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

        try:
            # 遍历 Brave 搜索结果的容器 .snippet
            for element in soup.select(".snippet"):
                # 标题在 .title
                title_el = element.select_one(".title")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)

                # 提取第一个链接（a 标签的 href）
                link_el = element.select_one("a")
                raw_url = link_el.get("href", "") if link_el else ""

                # 提取 snippet（描述文本），多个可能的选择器
                snippet = ""
                for selector in [".snippet-description", ".snippet-content", ".description"]:
                    snippet_el = element.select_one(selector)
                    if snippet_el:
                        snippet = snippet_el.get_text(strip=True)
                        break

                # 过滤内部链接（/ 开头的相对路径）
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
        except Exception as e:
            logger.warning("Brave HTML 解析失败: %s", e)

        logger.info("Brave 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_BRAVE,
            results=results,
            total_results=len(results),
        )
