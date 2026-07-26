from __future__ import annotations
from datetime import date
import pytest
from souwen.providers.runtime_clients.models import PatentResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchRequest,
)
from souwen.providers.information_sources.cnipa import (
    CNIPA_BRIDGE_SPEC,
    CNIPA_PROVIDER_MANIFEST,
    CnipaSearchProvider,
)


class _Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, query, per_page=10, offset=0):
        self.calls.append((query, per_page, offset))
        return self.value

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_cnipa_oauth_bridge_maps_and_fails_closed() -> None:
    response = SearchResponse(
        query="battery",
        source="cnipa",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PatentResult(
                source="cnipa",
                patent_id="CN123A",
                title="Battery",
                publication_date=date(2024, 1, 1),
                source_url="https://open.cnipr.com/patent/CN123A",
            )
        ],
    )
    page = await CnipaSearchProvider(_Client(response)).search(
        SearchRequest(query="battery", domains=("patent",)),
        RequestContext(request_id="cnipa"),
        ExecutionContext.with_timeout(5),
    )
    assert page.items[0].id == "cnipa:CN123A"
    assert CNIPA_PROVIDER_MANIFEST.secrets.references == ("CNIPA_CLIENT_ID", "CNIPA_CLIENT_SECRET")
    assert tuple(item[0] for item in CNIPA_BRIDGE_SPEC.auth.reference_requirements) == (
        "CNIPA_CLIENT_ID",
        "CNIPA_CLIENT_SECRET",
    )
    with pytest.raises(ProviderError) as caught:
        await CnipaSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("patent",)),
            RequestContext(request_id="bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
