from __future__ import annotations
from datetime import date
import pytest
from souwen.models import PatentResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchRequest,
)
from souwen.providers.information_sources.the_lens import (
    THE_LENS_BRIDGE_SPEC,
    THE_LENS_PROVIDER_MANIFEST,
    TheLensSearchProvider,
)


class _Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search_patents(self, query, size=10, offset=0):
        self.calls.append((query, size, offset))
        return self.value

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_the_lens_bridge_maps_lens_identity_and_bearer_contract() -> None:
    response = SearchResponse(
        query="battery",
        source="the_lens",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PatentResult(
                source="the_lens",
                patent_id="US123",
                title="Battery",
                publication_date=date(2024, 1, 1),
                source_url="https://www.lens.org/lens/patent/LENS-1",
                raw={"lens_id": "LENS-1"},
            )
        ],
    )
    client = _Client(response)
    page = await TheLensSearchProvider(client).search(
        SearchRequest(query="battery", domains=("patent",)),
        RequestContext(request_id="lens"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("battery", 10, 0)] and page.items[0].id == "the_lens:LENS-1"
    assert (
        THE_LENS_PROVIDER_MANIFEST.secrets.references == ("LENS_API_TOKEN",)
        and THE_LENS_BRIDGE_SPEC.auth.placement == "bearer"
    )
    with pytest.raises(ProviderError) as caught:
        await TheLensSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("patent",)),
            RequestContext(request_id="bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
