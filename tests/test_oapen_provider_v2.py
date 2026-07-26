from __future__ import annotations
import pytest
from souwen.models import BookResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.oapen import (
    OAPEN_PROVIDER_MANIFEST,
    OAPEN_PROVIDER_SPEC,
    OAPENSearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(self, query: str, per_page: int = 10, page: int = 1):
        self.calls.append((query, per_page, page))
        return self.response


@pytest.mark.asyncio
async def test_oapen_search_keeps_bounded_first_page_only() -> None:
    client = _Client(
        SearchResponse(
            query="catalog",
            source="oapen",
            total_results=None,
            per_page=10,
            results=[
                BookResult(
                    source="oapen",
                    source_record_id="20.500.12657/1",
                    title="Catalog",
                    source_url="https://library.oapen.org/handle/20.500.12657/1",
                )
            ],
        )
    )
    page = await OAPENSearchProvider(client).search(
        SearchRequest(query="catalog", domains=("book",)),
        RequestContext(request_id="oapen"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("catalog", 10, 1)]
    assert page.items[0].id == "oapen:20.500.12657/1"
    assert OAPEN_PROVIDER_MANIFEST.network.egress_hosts == ("library.oapen.org",)
    assert OAPEN_PROVIDER_SPEC.transport.protocol == "xml"
