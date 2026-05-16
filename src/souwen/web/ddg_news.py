"""DuckDuckGo 新闻搜索

通过 duckduckgo.com/news.js JSON 端点获取新闻搜索结果。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from souwen.models import WebSearchResult, WebSearchResponse
from souwen.web.ddg_json import DDGJsonClient
from souwen.web.ddg_utils import normalize_text

logger = logging.getLogger("souwen.web.ddg_news")

# safesearch 映射 → DDG news.js 的 p 参数
_SAFESEARCH_MAP = {"on": "1", "moderate": "-1", "off": "-2"}


class DuckDuckGoNewsClient(DDGJsonClient):
    """DuckDuckGo 新闻搜索客户端

    使用 news.js JSON 端点，支持时间范围过滤和区域设置。
    """

    ENGINE_NAME = "duckduckgo_news"
    _ENDPOINT = "/news.js"
    _MAX_PAGES = 5

    async def search(
        self,
        query: str,
        max_results: int = 20,
        region: str = "wt-wt",
        safesearch: str = "moderate",
        time_range: str | None = None,
        max_pages: int | None = None,
    ) -> WebSearchResponse:
        """搜索 DuckDuckGo 新闻

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            region: 区域代码
            safesearch: "on"/"moderate"/"off"
            time_range: "d"(天)/"w"(周)/"m"(月)/None
            max_pages: 最大分页数

        Returns:
            WebSearchResponse 包含新闻搜索结果
        """
        vqd = await self._get_vqd(query)
        if not vqd:
            logger.warning("无法获取 VQD token，返回空结果")
            return WebSearchResponse(
                query=query,
                source="duckduckgo_news",
                results=[],
                total_results=0,
            )

        params: dict[str, str] = {
            "l": region,
            "o": "json",
            "noamp": "1",
            "q": query,
            "vqd": vqd,
            "p": _SAFESEARCH_MAP.get(safesearch, "-1"),
        }
        if time_range:
            params["df"] = time_range

        raw_results = await self._paginated_search(query, params, max_results, max_pages)

        results: list[WebSearchResult] = []
        seen_urls: set[str] = set()

        for row in raw_results:
            url = row.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = row.get("title", "")
            body = normalize_text(row.get("excerpt", ""))
            source_name = row.get("source", "")

            # 格式化日期
            date_str = ""
            ts = row.get("date")
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                    date_str = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError, OSError):
                    pass

            snippet_parts = []
            if source_name:
                snippet_parts.append(f"📰 {source_name}")
            if date_str:
                snippet_parts.append(date_str)
            if body:
                snippet_parts.append(body)
            snippet = " | ".join(snippet_parts)

            if title:
                results.append(
                    WebSearchResult(
                        source="duckduckgo_news",
                        title=title,
                        url=url,
                        snippet=snippet,
                        engine=self.ENGINE_NAME,
                    )
                )

        logger.info("DDG News 返回 %d 条结果 (query=%s)", len(results), query)
        return WebSearchResponse(
            query=query,
            source="duckduckgo_news",
            results=results,
            total_results=len(results),
        )
