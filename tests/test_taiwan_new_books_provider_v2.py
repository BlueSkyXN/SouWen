from __future__ import annotations
import pytest
from souwen.models import BookIdentifier, BookResult, ResourceAccess, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.taiwan_new_books import (
    TAIWAN_NEW_BOOKS_PROVIDER_MANIFEST,
    TAIWAN_NEW_BOOKS_PROVIDER_SPEC,
    TaiwanNewBooksSearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(self, query: str, per_page: int = 10):
        self.calls.append((query, per_page))
        return self.response


@pytest.mark.asyncio
async def test_taiwan_new_books_search_projects_isbn_metadata_without_page_or_egress() -> None:
    client = _Client(
        SearchResponse(
            query="新書",
            source="taiwan_new_books",
            total_results=1,
            per_page=10,
            results=[
                BookResult(
                    source="taiwan_new_books",
                    source_record_id="9789861234567",
                    title="新書",
                    identifiers=[BookIdentifier(scheme="isbn13", value="9789861234567")],
                    access=ResourceAccess(status="metadata_only"),
                    source_url="https://data.gov.tw/api/front/dataset/detail?nid=6730",
                )
            ],
        )
    )
    page = await TaiwanNewBooksSearchProvider(client).search(
        SearchRequest(query="新書", domains=("book",)),
        RequestContext(request_id="taiwan"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("新書", 10)]
    assert page.items[0].attributes.identifiers[0].scheme == "isbn13"
    assert page.items[0].attributes.open_access is None
    assert TAIWAN_NEW_BOOKS_PROVIDER_MANIFEST.network.egress_hosts == ()
    assert TAIWAN_NEW_BOOKS_PROVIDER_SPEC.transport.store == "local_catalog"
