"""CSDN 搜索客户端

文件用途：
    CSDN（中国最大开发者社区）搜索客户端。通过 CSDN 内部搜索 API
    检索技术博客文章，无需 API Key。返回结果统一映射为 SouWen
    的 WebSearchResult 模型。

    本客户端继承 BaseScraper —— 目的是复用其 TLS 指纹伪装、
    浏览器级请求头、自适应限速与自动重试能力，避免被风控。

    注意：CSDN 搜索 API 为非公开接口，可能随时变更。

函数/类清单：
    CSDNClient（类）
        - 功能：CSDN 搜索客户端
        - 继承：BaseScraper
        - 关键属性：ENGINE_NAME = "csdn",
                  BASE_URL = "https://so.csdn.net/api/v3/search"
        - 主要方法：search(query, max_results) -> WebSearchResponse

模块依赖：
    - logging: 日志记录
    - re: HTML 标签清理
    - souwen.models: str, WebSearchResult, WebSearchResponse
    - souwen.core.scraper.base: BaseScraper
"""

from __future__ import annotations

import logging
import re

from souwen.models import WebSearchResult, WebSearchResponse
from souwen.core.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.csdn")

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str) -> str:
    """移除 HTML 标签（如 <em> 高亮标记）"""
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()


class CSDNClient(BaseScraper):
    """CSDN 搜索客户端

    中国最大的开发者博客平台，通过内部搜索 API 获取结果。
    无需 API Key，零配置即可使用。
    """

    ENGINE_NAME = "csdn"
    BASE_URL = "https://so.csdn.net/api/v3/search"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索 CSDN 博客文章

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（默认 20）

        Returns:
            WebSearchResponse 包含搜索结果
        """
        results: list[WebSearchResult] = []
        page = 1
        max_pages = (max_results + 19) // 20  # 每页约 20 条

        while len(results) < max_results and page <= max_pages:
            try:
                resp = await self._fetch(
                    self._resolved_base_url,
                    params={"q": query, "p": str(page)},
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "Referer": f"https://so.csdn.net/so/search?q={query}",
                        "Origin": "https://so.csdn.net",
                    },
                )

                data = resp.json()

                # CSDN API 返回格式：{"result_vos": [...], ...}
                result_vos = data.get("result_vos")
                if not result_vos or not isinstance(result_vos, list):
                    logger.debug("CSDN 第 %d 页无结果", page)
                    break

                for item in result_vos:
                    if len(results) >= max_results:
                        break

                    title = _clean_html(item.get("title", ""))
                    url = item.get("url_location") or item.get("url", "")
                    digest = _clean_html(item.get("digest", ""))
                    nickname = item.get("nickname", "")

                    if not title or not url:
                        continue

                    snippet = digest
                    if nickname:
                        snippet = f"{digest} — 作者: {nickname}"

                    results.append(
                        WebSearchResult(
                            source="csdn",
                            title=title,
                            url=url,
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                if len(result_vos) == 0:
                    break

                page += 1

            except Exception as e:
                logger.warning("CSDN 搜索第 %d 页失败: %s", page, e)
                break

        logger.info("CSDN 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="csdn",
            results=results,
            total_results=len(results),
        )
