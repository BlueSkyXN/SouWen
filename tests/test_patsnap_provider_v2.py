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
from souwen.providers.information_sources.patsnap import (
    PATSNAP_BRIDGE_SPEC,
    PATSNAP_PROVIDER_MANIFEST,
    PatSnapSearchProvider,
)


class _Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, query, limit=10, offset=0):
        self.calls.append((query, limit, offset))
        return self.value

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_patsnap_bridge_maps_required_key_search() -> None:
    response = SearchResponse(
        query="battery",
        source="patsnap",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PatentResult(
                source="patsnap",
                patent_id="US123",
                title="Battery",
                publication_date=date(2024, 1, 1),
                source_url="https://connect.patsnap.com/patent/US123",
            )
        ],
    )
    client = _Client(response)
    page = await PatSnapSearchProvider(client).search(
        SearchRequest(query="battery", domains=("patent",)),
        RequestContext(request_id="patsnap"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("battery", 10, 0)] and page.items[0].id == "patsnap:US123"
    assert (
        PATSNAP_PROVIDER_MANIFEST.secrets.references == ("PATSNAP_API_KEY",)
        and PATSNAP_BRIDGE_SPEC.auth.field_name == "X-PatSnap-Key"
    )
    with pytest.raises(ProviderError) as caught:
        await PatSnapSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("patent",)),
            RequestContext(request_id="bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
