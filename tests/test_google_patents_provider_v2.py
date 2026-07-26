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
from souwen.providers.information_sources.google_patents import (
    GOOGLE_PATENTS_BRIDGE_SPEC,
    GOOGLE_PATENTS_PROVIDER_MANIFEST,
    GooglePatentsSearchProvider,
)


class _Client:
    def __init__(self, response):
        self.response, self.calls, self.closed = response, [], 0

    async def search(self, query, num_results=10):
        self.calls.append((query, num_results))
        return self.response

    async def close(self):
        self.closed += 1


@pytest.mark.asyncio
async def test_google_patents_bridge_preserves_legacy_query_and_patent_identity() -> None:
    response = SearchResponse(
        query="battery",
        source="google_patents",
        total_results=1,
        results=[
            PatentResult(
                source="google_patents",
                patent_id="US1234567A",
                title="Battery",
                abstract="Fixture",
                publication_date=date(2024, 1, 2),
                source_url="https://patents.google.com/patent/US1234567A/en",
            )
        ],
    )
    client = _Client(response)
    page = await GooglePatentsSearchProvider(client).search(
        SearchRequest(query="battery", domains=("patent",)),
        RequestContext(request_id="google"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("battery", 10)]
    assert page.items[0].id == "google_patents:US1234567A"
    assert GOOGLE_PATENTS_BRIDGE_SPEC.transport.protocol == "multi_transport"
    assert GOOGLE_PATENTS_PROVIDER_MANIFEST.network.browser_required is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("page", "per_page"), ((2, 10), (1, 9)))
async def test_google_patents_bridge_rejects_mismatched_legacy_page_metadata(
    page: int, per_page: int
) -> None:
    response = SearchResponse(
        query="battery",
        source="google_patents",
        total_results=0,
        page=page,
        per_page=per_page,
        results=[],
    )

    with pytest.raises(ProviderError) as caught:
        await GooglePatentsSearchProvider(_Client(response)).search(
            SearchRequest(query="battery", domains=("patent",)),
            RequestContext(request_id="google-page"),
            ExecutionContext.with_timeout(5),
        )

    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
