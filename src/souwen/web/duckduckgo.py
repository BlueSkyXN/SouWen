"""DuckDuckGo HTML 搜索引擎

文件用途：
    DuckDuckGo 轻量 HTML 搜索引擎爬虫客户端。使用 HTML 版本避免 JavaScript 依赖，
    通过重定向参数解码获取真实 URL，无需 API Key。

函数/类清单：
    DuckDuckGoClient（类）
        - 功能：DuckDuckGo HTML 版本爬虫客户端，通过 CSS 选择器解析搜索结果
        - 继承：BaseScraper（基础爬虫类）
        - 关键属性：ENGINE_NAME = "duckduckgo", BASE_URL = "https://html.duckduckgo.com/html/",
                  min_delay = 1.0, max_delay = 3.0, max_retries = 3
        - 主要方法：search(query, max_results) -> WebSearchResponse

    DuckDuckGoClient.__init__(**kwargs)
        - 功能：初始化 DuckDuckGo 搜索客户端
        - 输入：**kwargs 传递给 BaseScraper 的参数
        - 输出：实例

    DuckDuckGoClient.search(query, max_results=20) -> WebSearchResponse
        - 功能：查询 DuckDuckGo，返回聚合结果
        - 输入：query 搜索关键词, max_results 最大返回结果数（默认20）
        - 输出：WebSearchResponse 包含搜索结果

    DuckDuckGoClient._decode_ddg_url(url) -> str
        - 功能：解码 DuckDuckGo 重定向 URL（从 uddg= 参数提取真实 URL）
        - 输入：url DuckDuckGo 格式的 URL 字符串
        - 输出：解码后的真实 URL

模块依赖：
    - logging: 日志记录
    - urllib.parse: URL 编码/解码
    - bs4: HTML 解析
    - souwen.models: SourceType, WebSearchResult, WebSearchResponse 数据模型
    - souwen.scraper.base: BaseScraper 基础爬虫类

技术要点：
    - 使用 HTML 版本避免 JavaScript 渲染
    - CSS 选择器：.result（结果容器）、.result__a（标题）、.result__snippet（描述）
    - 解码 DuckDuckGo 重定向 URL：//duckduckgo.com/l/?uddg=ENCODED_URL&rut=...
    - URL 必须是 http/https 开头（过滤相对路径）
"""

from __future__ import annotations

import logging
from urllib.parse import unquote, quote_plus

from bs4 import BeautifulSoup

from souwen.models import SourceType, WebSearchResult, WebSearchResponse
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.duckduckgo")


class DuckDuckGoClient(BaseScraper):
    """DuckDuckGo HTML 搜索客户端

    使用 html.duckduckgo.com 轻量版本，无需 JavaScript 渲染。
    通过 CSS 选择器解析搜索结果。
    """

    ENGINE_NAME = "duckduckgo"
    BASE_URL = "https://html.duckduckgo.com/html/"

    def __init__(self, **kwargs):
        # 初始化爬虫配置：最小延迟 1.0s、最大延迟 3.0s、最多重试 3 次
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 DuckDuckGo

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
            # 遍历 DuckDuckGo 搜索结果的容器 .result
            for element in soup.select(".result"):
                # 标题在 .result__a
                title_el = element.select_one(".result__a")
                if title_el is None:
                    continue

                title = title_el.get_text(strip=True)
                raw_url = title_el.get("href", "")

                # 提取 snippet（描述文本）
                snippet_el = element.select_one(".result__snippet")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                # DuckDuckGo URL 重定向解码
                # 格式: //duckduckgo.com/l/?uddg=ENCODED_URL&rut=...
                real_url = self._decode_ddg_url(str(raw_url))

                # 过滤非 HTTP 链接
                if not real_url or not real_url.startswith(("http://", "https://")):
                    continue

                if title:
                    results.append(
                        WebSearchResult(
                            source=SourceType.WEB_DUCKDUCKGO,
                            title=title,
                            url=real_url,
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(results) >= max_results:
                    break
        except Exception as e:
            logger.warning("DuckDuckGo HTML 解析失败: %s", e)

        logger.info("DuckDuckGo 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source=SourceType.WEB_DUCKDUCKGO,
            results=results,
            total_results=len(results),
        )

    @staticmethod
    def _decode_ddg_url(url: str) -> str:
        """解码 DuckDuckGo 重定向 URL

        DuckDuckGo 通过 //duckduckgo.com/l/?uddg=ENCODED_URL 跳转。
        提取真实 URL 并解码。

        Args:
            url: DuckDuckGo 格式的 URL 字符串（可能包含 uddg 重定向参数）

        Returns:
            str: 解码后的真实 URL；不是重定向格式则返回原 URL
        """
        if url.startswith("//duckduckgo.com/l/?uddg="):
            # 提取 uddg= 之后的部分（& 前面的内容）
            parts = url.split("uddg=", 1)
            if len(parts) > 1:
                # 获取编码的 URL，忽略后续参数（& 分隔）
                encoded = parts[1].split("&", 1)[0]
                # URL 解码还原真实链接
                return unquote(encoded)
        return url
