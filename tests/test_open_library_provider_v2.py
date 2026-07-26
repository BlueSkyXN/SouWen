from __future__ import annotations
import pytest
from souwen.models import Author, BookIdentifier, BookResult, ResourceAccess, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.open_library import (
    OPEN_LIBRARY_PROVIDER_MANIFEST,
    OPEN_LIBRARY_PROVIDER_SPEC,
    OpenLibrarySearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(self, query: str, per_page: int = 10, page: int = 1):
        self.calls.append((query, per_page, page))
        return self.response


@pytest.mark.asyncio
async def test_open_library_search_projects_book_metadata_without_detail() -> None:
    client = _Client(
        SearchResponse(
            query="catalog",
            source="open_library",
            total_results=1,
            per_page=10,
            results=[
                BookResult(
                    source="open_library",
                    source_record_id="OL1W",
                    title="Catalog",
                    authors=[Author(name="Ada")],
                    first_publish_year=2024,
                    languages=["en"],
                    identifiers=[BookIdentifier(scheme="olid", value="OL1W")],
                    access=ResourceAccess(status="open_access"),
                    source_url="https://openlibrary.org/works/OL1W",
                )
            ],
        )
    )
    page = await OpenLibrarySearchProvider(client).search(
        SearchRequest(query="catalog", domains=("book",)),
        RequestContext(request_id="open-library"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("catalog", 10, 1)]
    assert page.items[0].id == "open_library:OL1W"
    assert page.items[0].attributes.resource_type == "book"
    assert page.items[0].attributes.open_access is True
    assert OPEN_LIBRARY_PROVIDER_MANIFEST.network.egress_hosts == ("openlibrary.org",)
    assert OPEN_LIBRARY_PROVIDER_SPEC.transport.host == "openlibrary.org"
