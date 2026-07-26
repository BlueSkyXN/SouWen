from __future__ import annotations
import pytest
from souwen.providers.runtime_clients.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.hostloc import (
    HOSTLOC_PROVIDER_MANIFEST,
    HOSTLOC_PROVIDER_SPEC,
    HostLocSearchProvider,
)


class _Client:
    async def search(self, query, max_results=20):
        self.call = (query, max_results)
        return SearchResponse(
            query=query,
            source="hostloc",
            total_results=1,
            results=[
                WebSearchResult(
                    source="hostloc",
                    title="Forum",
                    url="https://hostloc.com/thread-1-1-1.html",
                    snippet="text",
                    engine="hostloc",
                )
            ],
        )


@pytest.mark.asyncio
async def test_hostloc_search_uses_ddg_egress_but_target_domain_results():
    client = _Client()
    page = await HostLocSearchProvider(client).search(
        SearchRequest(query="server", domains=("cn_tech",), page=SearchPageRequest(limit=2)),
        RequestContext(request_id="hostloc"),
        ExecutionContext.with_timeout(1),
    )
    assert client.call == ("server", 2)
    assert str(page.items[0].url).startswith("https://hostloc.com/")
    assert HOSTLOC_PROVIDER_MANIFEST.network.egress_hosts == ("html.duckduckgo.com",)
    assert HOSTLOC_PROVIDER_SPEC.host == "html.duckduckgo.com"
