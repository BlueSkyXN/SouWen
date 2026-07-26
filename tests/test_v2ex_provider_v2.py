from __future__ import annotations
import pytest
from souwen.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.v2ex import (
    V2EX_PROVIDER_MANIFEST,
    V2EX_PROVIDER_SPEC,
    V2EXSearchProvider,
)


class _Client:
    async def search(self, query, max_results=20):
        self.call = (query, max_results)
        return SearchResponse(
            query=query,
            source="v2ex",
            total_results=1,
            results=[
                WebSearchResult(
                    source="v2ex",
                    title="Topic",
                    url="https://www.v2ex.com/t/1",
                    snippet="text",
                    engine="v2ex",
                )
            ],
        )


@pytest.mark.asyncio
async def test_v2ex_search_projects_reviewed_site_result():
    client = _Client()
    page = await V2EXSearchProvider(client).search(
        SearchRequest(query="python", domains=("cn_tech",), page=SearchPageRequest(limit=2)),
        RequestContext(request_id="v2ex"),
        ExecutionContext.with_timeout(1),
    )
    assert client.call == ("python", 2)
    assert str(page.items[0].url).startswith("https://www.v2ex.com/")
    assert V2EX_PROVIDER_MANIFEST.network.egress_hosts == ("html.duckduckgo.com",)
    assert V2EX_PROVIDER_SPEC.host == "html.duckduckgo.com"
