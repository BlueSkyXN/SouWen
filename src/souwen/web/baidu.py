"""Baidu 搜索引擎

文件用途：
    百度搜索引擎爬虫客户端。百度是中国最大的搜索引擎，
    提供中文搜索结果质量高，无需 API Key，适合中文搜索场景。

函数/类清单：
    BaiduClient（类）
        - 功能：百度搜索爬虫客户端，通过 HTML 解析获取搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "baidu", BASE_URL = "https://www.baidu.com/s",
                  min_delay = 1.0, max_delay = 3.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    BaiduClient.__init__(**kwargs)
        - 功能：初始化百度搜索客户端
        - 输入：**kwargs 传递给 BaseScraper 的参数
        - 输出：实例

    BaiduClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询百度搜索，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码
    - bs4: HTML 解析
    - souwen.models: str, WebSearchResult, WebSearchResponse 数据模型
    - souwen.core.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 CSS 选择器解析搜索结果容器
    - 百度使用重定向 URL，直接保留 href 即可
    - 支持多个选择器降级策略（snippet 提取）
    - 异常处理确保 HTML 解析错误不影响整体运行
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from souwen.models import WebSearchResult, WebSearchResponse
from souwen.core.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.baidu")


class BaiduClient(BaseScraper):
    """Baidu 搜索客户端

    百度搜索引擎，中文搜索首选。
    通过 CSS 选择器解析搜索结果。
    注意：百度使用重定向 URL，直接使用 href 值。
    """

    ENGINE_NAME = "baidu"
    BASE_URL = "https://www.baidu.com/s"

    def __init__(self, **kwargs):
        # 初始化爬虫配置：最小延迟 1.0s、最大延迟 3.0s、最多重试 3 次
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Baidu

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        url = f"{self._resolved_base_url}?wd={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # 遍历百度搜索结果的容器元素 div.c-container[id]
            for element in soup.select("div.c-container[id]"):
                # 提取标题和链接。标题在 .t > a 或 h3.t a
                title_el = element.select_one(".t > a") or element.select_one("h3.t a")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)
                # 百度使用重定向 URL，直接使用 href
                raw_url = title_el.get("href", "")

                # 提取 snippet（描述文本），尝试多个选择器
                snippet = ""
                snippet_el = element.select_one(".c-abstract")
                if snippet_el is None:
                    snippet_el = element.select_one(".c-span-last")
                if snippet_el is None:
                    snippet_el = element.select_one("p")
                if snippet_el:
                    snippet = snippet_el.get_text(strip=True)

                if not title:
                    continue

                results.append(
                    WebSearchResult(
                        source="baidu",
                        title=title,
                        url=str(raw_url),
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Baidu HTML 解析失败: %s", e)

        logger.info("Baidu 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="baidu",
            results=results,
            total_results=len(results),
        )
