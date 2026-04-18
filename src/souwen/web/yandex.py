"""Yandex 搜索引擎爬虫

文件用途：
    Yandex 搜索引擎爬虫客户端。Yandex 是俄罗斯最大的搜索引擎，
    拥有独立的搜索索引，无需 API Key，反爬虫机制较强。

函数/类清单：
    YandexClient（类）
        - 功能：Yandex 搜索爬虫客户端，通过 HTML 解析获取搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "yandex", BASE_URL = "https://yandex.com/search/",
                  min_delay = 2.0, max_delay = 5.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    YandexClient.__init__(**kwargs)
        - 功能：初始化 Yandex 搜索客户端
        - 输入：**kwargs 传递给 BaseScraper 的参数

    YandexClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询 Yandex 搜索，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码
    - bs4: HTML 解析
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型
    - souwen.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 CSS 选择器 li.serp-item 和 .OrganicResult 定位结果
    - 支持多套选择器降级策略（标题和摘要各两个备选选择器）
    - 反爬虫较强，设置较长的请求延迟（2.0-5.0s）
    - 仅保留 http/https 开头的有效 URL
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
        # 构建搜索 URL（text 参数为查询关键词）
        url = f"{self.BASE_URL}?text={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # 遍历 Yandex 搜索结果容器（两套选择器降级）
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

                # 过滤非 http/https 的无效 URL
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
