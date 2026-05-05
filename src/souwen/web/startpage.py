"""Startpage 隐私搜索引擎爬虫

文件用途：
    Startpage 搜索引擎爬虫客户端。Startpage 使用 Google 搜索结果但不追踪用户，
    无需 API Key，适合需要 Google 质量搜索且注重隐私的场景。

函数/类清单：
    StartpageClient（类）
        - 功能：Startpage 搜索爬虫客户端，通过 HTML 解析获取搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "startpage",
                  BASE_URL = "https://www.startpage.com/sp/search",
                  min_delay = 1.0, max_delay = 3.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    StartpageClient.__init__(**kwargs)
        - 功能：初始化 Startpage 搜索客户端
        - 输入：**kwargs 传递给 BaseScraper 的参数

    StartpageClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询 Startpage 搜索，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码
    - bs4: HTML 解析
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型
    - souwen.core.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 CSS 选择器 .w-gl__result 定位搜索结果容器
    - 标题在 .w-gl__result-title 中，描述在 .w-gl__description 中
    - 链接直接在 a.w-gl__result-title 的 href 属性中（无重定向）
    - 仅保留 http/https 开头的有效 URL
"""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.core.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.startpage")


class StartpageClient(BaseScraper):
    """Startpage 搜索客户端

    Startpage 使用 Google 搜索结果，但不追踪用户。
    通过 CSS 选择器解析搜索结果。
    """

    ENGINE_NAME = "startpage"
    BASE_URL = "https://www.startpage.com/sp/search"

    def __init__(self, **kwargs):
        # 初始化爬虫配置：最小延迟 1.0s、最大延迟 3.0s、最多重试 3 次
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 Startpage

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数

        Returns:
            WebSearchResponse 包含搜索结果
        """
        # 构建搜索 URL（query 参数为查询关键词）
        url = f"{self._resolved_base_url}?query={quote_plus(query)}"

        resp = await self._fetch(url)
        html = resp.text

        soup = BeautifulSoup(html, "lxml")
        results: list[WebSearchResult] = []

        try:
            # 遍历 Startpage 搜索结果容器
            for element in soup.select(".w-gl__result"):
                title_el = element.select_one(".w-gl__result-title")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)

                # 提取链接
                link_el = element.select_one("a.w-gl__result-title")
                raw_url = link_el.get("href", "") if link_el else ""

                # 提取 snippet
                snippet_el = element.select_one(".w-gl__description")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                # 过滤非 http/https 的无效 URL
                if not raw_url or not raw_url.startswith(("http://", "https://")):
                    continue

                if title:
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_STARTPAGE,
                            title=title,
                            url=str(raw_url),
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("Startpage HTML 解析失败: %s", e)

        logger.info("Startpage 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_STARTPAGE,
            results=results,
            total_results=len(results),
        )
