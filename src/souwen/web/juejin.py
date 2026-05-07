"""稀土掘金搜索客户端

文件用途：
    稀土掘金（juejin.cn）搜索客户端。通过掘金内部搜索 API
    检索技术文章，无需 API Key。返回结果统一映射为 SouWen
    的 WebSearchResult 模型。

    本客户端继承 BaseScraper —— 目的是复用其 TLS 指纹伪装、
    浏览器级请求头、自适应限速与自动重试能力。

函数/类清单：
    JuejinClient（类）
        - 功能：稀土掘金搜索客户端
        - 继承：BaseScraper
        - 关键属性：ENGINE_NAME = "juejin",
                  BASE_URL = "https://api.juejin.cn/search_api/v1/search"
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

logger = logging.getLogger("souwen.web.juejin")

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str) -> str:
    """移除 HTML 标签（如 <em> 高亮标记）"""
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()


class JuejinClient(BaseScraper):
    """稀土掘金搜索客户端

    中国热门技术社区，通过内部搜索 API 获取文章结果。
    无需 API Key，零配置即可使用。

    API 返回结构化数据，包含：文章标题、摘要、分类、标签、
    点赞数、阅读数、作者信息等。
    """

    ENGINE_NAME = "juejin"
    BASE_URL = "https://api.juejin.cn/search_api/v1/search"

    def __init__(self, **kwargs):
        super().__init__(min_delay=1.0, max_delay=3.0, max_retries=3, **kwargs)

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        """搜索稀土掘金文章

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（默认 20）

        Returns:
            WebSearchResponse 包含搜索结果
        """
        results: list[WebSearchResult] = []
        cursor = "0"

        while len(results) < max_results:
            try:
                batch_size = min(20, max_results - len(results))

                resp = await self._fetch(
                    self._resolved_base_url,
                    params={
                        "aid": "2608",
                        "uuid": "7259393293459605051",
                        "query": query,
                        "id_type": "0",
                        "cursor": cursor,
                        "limit": str(batch_size),
                        "search_type": "0",
                        "sort_type": "0",
                        "version": "1",
                    },
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "Content-Type": "application/json",
                        "Referer": "https://juejin.cn/",
                        "Origin": "https://juejin.cn",
                    },
                )

                data = resp.json()

                if data.get("err_no") != 0:
                    logger.warning("Juejin API 错误: %s", data.get("err_msg", "unknown"))
                    break

                items = data.get("data")
                if not items or not isinstance(items, list):
                    break

                for item in items:
                    if len(results) >= max_results:
                        break

                    result_model = item.get("result_model", {})
                    article_info = result_model.get("article_info", {})
                    author_info = result_model.get("author_user_info", {})
                    category = result_model.get("category", {})
                    tags = result_model.get("tags", [])

                    # 优先使用高亮标题，退而用原始标题
                    title = _clean_html(
                        item.get("title_highlight", "") or article_info.get("title", "")
                    )
                    article_id = result_model.get("article_id", "")

                    if not title or not article_id:
                        continue

                    url = f"https://juejin.cn/post/{article_id}"

                    # 构建 snippet
                    brief = _clean_html(
                        item.get("content_highlight", "") or article_info.get("brief_content", "")
                    )
                    tag_names = ", ".join(t.get("tag_name", "") for t in tags if t.get("tag_name"))
                    cat_name = category.get("category_name", "")
                    author_name = author_info.get("user_name", "")
                    digg_count = article_info.get("digg_count", 0)
                    view_count = article_info.get("view_count", 0)

                    parts = [brief]
                    if cat_name:
                        parts.append(f"分类: {cat_name}")
                    if tag_names:
                        parts.append(f"标签: {tag_names}")
                    if author_name:
                        parts.append(f"作者: {author_name}")
                    if digg_count or view_count:
                        parts.append(f"👍{digg_count} 👀{view_count}")

                    snippet = " | ".join(p for p in parts if p)

                    results.append(
                        WebSearchResult(
                            source="juejin",
                            title=title,
                            url=url,
                            snippet=snippet,
                            engine=self.ENGINE_NAME,
                        )
                    )

                # 检查是否有下一页
                has_more = data.get("has_more", False)
                next_cursor = data.get("cursor", "")

                if not has_more or not next_cursor or len(items) == 0:
                    break

                cursor = next_cursor

            except Exception as e:
                logger.warning("Juejin 搜索失败 (cursor=%s): %s", cursor, e)
                break

        logger.info("Juejin 返回 %d 条结果 (query=%s)", len(results), query)

        return WebSearchResponse(
            query=query,
            source="juejin",
            results=results,
            total_results=len(results),
        )
