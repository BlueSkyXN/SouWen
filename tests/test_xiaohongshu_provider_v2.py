from __future__ import annotations
import pytest
from souwen.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.xiaohongshu import (
    XIAOHONGSHU_PROVIDER_MANIFEST,
    XIAOHONGSHU_PROVIDER_SPEC,
    XiaohongshuSearchProvider,
)


class _Client:
    async def search(self, query, max_results=20):
        self.call = (query, max_results)
        return SearchResponse(
            query=query,
            source="xiaohongshu",
            total_results=1,
            results=[
                WebSearchResult(
                    source="xiaohongshu",
                    title="Note",
                    url="https://www.xiaohongshu.com/explore/1",
                    snippet="text",
                    engine="xiaohongshu",
                )
            ],
        )


@pytest.mark.asyncio
async def test_xiaohongshu_search_projects_reviewed_site_result():
    client = _Client()
    page = await XiaohongshuSearchProvider(client).search(
        SearchRequest(query="travel", domains=("cn_tech",), page=SearchPageRequest(limit=2)),
        RequestContext(request_id="xiaohongshu"),
        ExecutionContext.with_timeout(1),
    )
    assert client.call == ("travel", 2)
    assert page.items[0].id.startswith("xiaohongshu:")
    assert XIAOHONGSHU_PROVIDER_MANIFEST.network.egress_hosts == ("html.duckduckgo.com",)
    assert XIAOHONGSHU_PROVIDER_SPEC.host == "html.duckduckgo.com"
