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
from souwen.providers.information_sources.uspto_odp import (
    USPTO_ODP_BRIDGE_SPEC,
    USPTO_ODP_PROVIDER_MANIFEST,
    UsptoOdpSearchProvider,
)


class _Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search_applications(self, query, per_page=10, offset=0):
        self.calls.append((query, per_page, offset))
        return self.value

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_uspto_odp_bridge_maps_application_search_and_header_contract() -> None:
    response = SearchResponse(
        query="battery",
        source="uspto_odp",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PatentResult(
                source="uspto_odp",
                patent_id="US123",
                title="Battery",
                publication_date=date(2024, 1, 1),
                source_url="https://data.uspto.gov/patent/US123",
            )
        ],
    )
    client = _Client(response)
    page = await UsptoOdpSearchProvider(client).search(
        SearchRequest(query="battery", domains=("patent",)),
        RequestContext(request_id="uspto"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("battery", 10, 0)] and page.items[0].id == "uspto_odp:US123"
    assert (
        USPTO_ODP_PROVIDER_MANIFEST.secrets.references == ("USPTO_API_KEY",)
        and USPTO_ODP_BRIDGE_SPEC.auth.field_name == "X-API-Key"
    )
    with pytest.raises(ProviderError) as caught:
        await UsptoOdpSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("patent",)),
            RequestContext(request_id="bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
