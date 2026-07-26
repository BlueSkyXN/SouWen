from __future__ import annotations
import pytest
from souwen.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.nodeseek import (
    NODESEEK_PROVIDER_MANIFEST,
    NODESEEK_PROVIDER_SPEC,
    NodeSeekSearchProvider,
)


class _Client:
    async def search(self, query, max_results=20):
        self.call = (query, max_results)
        return SearchResponse(
            query=query,
            source="nodeseek",
            total_results=1,
            results=[
                WebSearchResult(
                    source="nodeseek",
                    title="Node",
                    url="https://nodeseek.com/post-1-1",
                    snippet="text",
                    engine="nodeseek",
                )
            ],
        )


@pytest.mark.asyncio
async def test_nodeseek_search_projects_reviewed_site_result():
    client = _Client()
    page = await NodeSeekSearchProvider(client).search(
        SearchRequest(query="node", domains=("cn_tech",), page=SearchPageRequest(limit=2)),
        RequestContext(request_id="nodeseek"),
        ExecutionContext.with_timeout(1),
    )
    assert client.call == ("node", 2)
    assert page.items[0].provenance[0].provider == "nodeseek"
    assert NODESEEK_PROVIDER_MANIFEST.network.egress_hosts == ("html.duckduckgo.com",)
    assert NODESEEK_PROVIDER_SPEC.host == "html.duckduckgo.com"
