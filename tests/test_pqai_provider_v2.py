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
from souwen.providers.information_sources.pqai import (
    PQAI_BRIDGE_SPEC,
    PQAI_PROVIDER_MANIFEST,
    PqaiSearchProvider,
)


class _Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, query, n_results=10):
        self.calls.append((query, n_results))
        return self.value

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_pqai_bridge_maps_query_token_contract_without_exposing_it() -> None:
    response = SearchResponse(
        query="battery",
        source="pqai",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PatentResult(
                source="pqai",
                patent_id="US123",
                title="Battery",
                publication_date=date(2024, 1, 1),
                source_url="https://patents.google.com/patent/US123",
            )
        ],
    )
    client = _Client(response)
    page = await PqaiSearchProvider(client).search(
        SearchRequest(query="battery", domains=("patent",)),
        RequestContext(request_id="pqai"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("battery", 10)] and page.items[0].id == "pqai:US123"
    assert (
        PQAI_PROVIDER_MANIFEST.secrets.references == ("PQAI_API_TOKEN",)
        and PQAI_BRIDGE_SPEC.auth.field_name == "token"
    )
    with pytest.raises(ProviderError) as caught:
        await PqaiSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("patent",)),
            RequestContext(request_id="bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
