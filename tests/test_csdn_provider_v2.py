from __future__ import annotations
import pytest
from souwen.providers.runtime_clients.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.csdn import (
    CSDN_PROVIDER_MANIFEST,
    CSDN_PROVIDER_SPEC,
    CSDNSearchProvider,
)


class _Client:
    def __init__(self):
        self.calls = []

    async def search(self, query, max_results=20):
        self.calls.append((query, max_results))
        return SearchResponse(
            query=query,
            source="csdn",
            total_results=1,
            results=[
                WebSearchResult(
                    source="csdn",
                    title="Python",
                    url="https://blog.csdn.net/user/article/details/1",
                    snippet="text",
                    engine="csdn",
                )
            ],
        )


@pytest.mark.asyncio
async def test_csdn_search_projects_and_rejects_cursor_and_filters():
    client = _Client()
    provider = CSDNSearchProvider(client)
    request = SearchRequest(query="python", domains=("cn_tech",), page=SearchPageRequest(limit=3))
    page = await provider.search(
        request, RequestContext(request_id="csdn"), ExecutionContext.with_timeout(1)
    )
    assert client.calls == [("python", 3)]
    assert page.page.limit == 3
    for invalid in (
        SearchRequest(
            query="python", domains=("cn_tech",), page=SearchPageRequest(limit=3, cursor="x")
        ),
        SearchRequest(query="python", domains=("cn_tech",), filters={"language": "zh"}),
    ):
        with pytest.raises(ProviderError) as caught:
            await provider.search(
                invalid, RequestContext(request_id="invalid"), ExecutionContext.with_timeout(1)
            )
        assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert CSDN_PROVIDER_MANIFEST.network.egress_hosts == ("so.csdn.net",)
    assert CSDN_PROVIDER_SPEC.transport.operations[0].endpoint == "/api/v3/search"
