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
from souwen.providers.information_sources.epo_ops import (
    EPO_OPS_BRIDGE_SPEC,
    EPO_OPS_PROVIDER_MANIFEST,
    EpoOpsSearchProvider,
)


class _Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, cql_query, range_begin=1, range_end=10):
        self.calls.append((cql_query, range_begin, range_end))
        return self.value

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_epo_ops_oauth_bridge_preserves_cql_range_mapping() -> None:
    response = SearchResponse(
        query="ta=battery",
        source="epo_ops",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PatentResult(
                source="epo_ops",
                patent_id="EP123",
                title="Battery",
                publication_date=date(2024, 1, 1),
                source_url="https://worldwide.espacenet.com/patent/search?q=EP123",
            )
        ],
    )
    client = _Client(response)
    page = await EpoOpsSearchProvider(client).search(
        SearchRequest(query="ta=battery", domains=("patent",)),
        RequestContext(request_id="epo"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("ta=battery", 1, 10)] and page.items[0].id == "epo_ops:EP123"
    assert EPO_OPS_PROVIDER_MANIFEST.secrets.references == (
        "EPO_CONSUMER_KEY",
        "EPO_CONSUMER_SECRET",
    )
    assert tuple(item[0] for item in EPO_OPS_BRIDGE_SPEC.auth.reference_requirements) == (
        "EPO_CONSUMER_KEY",
        "EPO_CONSUMER_SECRET",
    )
    with pytest.raises(ProviderError) as caught:
        await EpoOpsSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("patent",)),
            RequestContext(request_id="bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
