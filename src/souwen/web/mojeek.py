"""Mojeek 搜索引擎

文件用途：
    Mojeek 搜索引擎爬虫客户端。Mojeek 是英国独立搜索引擎，
    拥有自己的爬虫和搜索索引（非 Google/Bing 代理），注重隐私。

函数/类清单：
    MojeekClient（类）
        - 功能：Mojeek 搜索爬虫客户端，通过 HTML 解析获取搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "mojeek", BASE_URL = "https://www.mojeek.com/search",
                  min_delay = 1.0, max_delay = 3.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    MojeekClient.__init__(**kwargs)
        - 功能：初始化 Mojeek 搜索客户端
        - 输入：**kwargs 传递给 BaseScraper 的参数
        - 输出：实例

    MojeekClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询 Mojeek，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码
    - bs4: HTML 解析
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型
    - souwen.core.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 CSS 选择器 ul.results-standard > li 定位结果容器
    - 标题在 a.title，snippet 在 p.s
    - URL 必须是 http/https 开头（过滤相对路径）
    - 独立索引提供差异化搜索结果
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.core.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.mojeek")


class MojeekClient(BaseScraper):
    """Mojeek 搜索客户端

    Mojeek 是英国独立搜索引擎，拥有自己的爬虫和索引。
    通过 CSS 选择器解析搜索结果。
    """

    ENGINE_NAME = "mojeek"
    BASE_URL = "https://www.mojeek.com/search"

    def __init__(self, **kwargs):
        # 初始化爬虫配置：最小延迟 1.0s、最大延迟 3.0s、最多重试 3 次
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Mojeek

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        url = f"{self._resolved_base_url}?q={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # 遍历 Mojeek 搜索结果的容器：ul.results-standard > li
            for element in soup.select("ul.results-standard > li"):
                # 提取标题和链接（a.title）
                title_el = element.select_one("a.title")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)
                raw_url = title_el.get("href", "")

                # 提取 snippet（描述文本，p.s）
                snippet_el = element.select_one("p.s")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                # 过滤非 HTTP 链接
                if not raw_url or not raw_url.startswith(("http://", "https://")):
                    continue

                if title:
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_MOJEEK,
                            title=title,
                            url=str(raw_url),
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Mojeek HTML 解析失败: %s", e)

        logger.info("Mojeek 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_MOJEEK,
            results=results,
            total_results=len(results),
        )
