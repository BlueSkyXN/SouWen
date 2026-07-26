from __future__ import annotations
import pytest
from souwen.models import BookResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.library_of_congress import (
    LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST,
    LIBRARY_OF_CONGRESS_PROVIDER_SPEC,
    LibraryOfCongressSearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(self, query: str, per_page: int = 10, page: int = 1):
        self.calls.append((query, per_page, page))
        return self.response


@pytest.mark.asyncio
async def test_library_of_congress_search_projects_only_catalog_fields() -> None:
    client = _Client(
        SearchResponse(
            query="catalog",
            source="library_of_congress",
            total_results=1,
            per_page=10,
            results=[
                BookResult(
                    source="library_of_congress",
                    source_record_id="abc",
                    title="Catalog",
                    source_url="https://www.loc.gov/item/abc/",
                )
            ],
        )
    )
    page = await LibraryOfCongressSearchProvider(client).search(
        SearchRequest(query="catalog", domains=("book",)),
        RequestContext(request_id="loc"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("catalog", 10, 1)]
    assert page.page.total == 1
    assert LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST.network.egress_hosts == ("www.loc.gov",)
    assert LIBRARY_OF_CONGRESS_PROVIDER_SPEC.transport.host == "www.loc.gov"
