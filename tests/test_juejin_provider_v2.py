from __future__ import annotations
import pytest
from souwen.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.juejin import (
    JUEJIN_PROVIDER_MANIFEST,
    JUEJIN_PROVIDER_SPEC,
    JuejinSearchProvider,
)


class _Client:
    async def search(self, query, max_results=20):
        self.call = (query, max_results)
        return SearchResponse(
            query=query,
            source="juejin",
            total_results=1,
            results=[
                WebSearchResult(
                    source="juejin",
                    title="Article",
                    url="https://juejin.cn/post/1",
                    snippet="text",
                    engine="juejin",
                )
            ],
        )


@pytest.mark.asyncio
async def test_juejin_search_remains_cursor_free_canonically():
    client = _Client()
    page = await JuejinSearchProvider(client).search(
        SearchRequest(query="python", domains=("cn_tech",), page=SearchPageRequest(limit=20)),
        RequestContext(request_id="juejin"),
        ExecutionContext.with_timeout(1),
    )
    assert client.call == ("python", 20)
    assert page.page.next_cursor is None
    assert JUEJIN_PROVIDER_MANIFEST.network.egress_hosts == ("api.juejin.cn",)
    assert JUEJIN_PROVIDER_SPEC.transport.operations[0].endpoint == "/search_api/v1/search"
