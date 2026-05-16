from __future__ import annotations

import logging

from souwen.core.http_client import SouWenHttpClient
from souwen.models import WebSearchResponse, WebSearchResult


class DdgSiteSearchClient(SouWenHttpClient):
    """基于 DuckDuckGo site:domain 的社区搜索基础客户端。"""

    ENGINE_NAME: str = "ddg_site"
    SITE_DOMAIN: str = ""
    SOURCE_TYPE: str = "duckduckgo"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ddg_client: object | None = None

    def _get_ddg_client(self):
        if self._ddg_client is None:
            from souwen.web.duckduckgo import DuckDuckGoClient

            self._ddg_client = DuckDuckGoClient()
        return self._ddg_client

    async def close(self) -> None:
        if self._ddg_client is not None:
            await self._ddg_client.close()
            self._ddg_client = None
        await super().close()

    async def search(self, query: str, max_results: int = 20) -> WebSearchResponse:
        logger = logging.getLogger(f"souwen.web.{self.ENGINE_NAME}")
        site_query = f"site:{self.SITE_DOMAIN} {query}"
        try:
            ddg = self._get_ddg_client()
            resp = await ddg.search(site_query, max_results=max_results, max_pages=1)
            results = [
                WebSearchResult(
                    source=self.SOURCE_TYPE,
                    title=item.title,
                    url=item.url,
                    snippet=item.snippet,
                    engine=self.ENGINE_NAME,
                    raw=item.raw,
                )
                for item in resp.results
            ]
        except Exception as e:
            logger.warning("%s 搜索失败: %s", self.ENGINE_NAME, e)
            results = []

        return WebSearchResponse(
            query=query,
            source=self.SOURCE_TYPE,
            total_results=len(results),
            results=results,
        )
