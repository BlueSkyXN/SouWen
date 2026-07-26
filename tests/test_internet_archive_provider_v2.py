from __future__ import annotations
import pytest
from souwen.providers.runtime_clients.models import BookResult, ResourceAccess, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.internet_archive import (
    INTERNET_ARCHIVE_PROVIDER_MANIFEST,
    INTERNET_ARCHIVE_PROVIDER_SPEC,
    InternetArchiveSearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(self, query: str, per_page: int = 10, page: int = 1):
        self.calls.append((query, per_page, page))
        return self.response


@pytest.mark.asyncio
async def test_internet_archive_search_does_not_expose_file_links() -> None:
    client = _Client(
        SearchResponse(
            query="catalog",
            source="internet_archive",
            total_results=1,
            per_page=10,
            results=[
                BookResult(
                    source="internet_archive",
                    source_record_id="item",
                    title="Catalog",
                    access=ResourceAccess(status="restricted"),
                    source_url="https://archive.org/details/item",
                )
            ],
        )
    )
    page = await InternetArchiveSearchProvider(client).search(
        SearchRequest(query="catalog", domains=("book",)),
        RequestContext(request_id="archive"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("catalog", 10, 1)]
    assert page.items[0].attributes.open_access is False
    assert "resources" not in page.items[0].model_dump()
    assert INTERNET_ARCHIVE_PROVIDER_MANIFEST.network.egress_hosts == ("archive.org",)
    assert INTERNET_ARCHIVE_PROVIDER_SPEC.transport.operations[0].endpoint == "/advancedsearch.php"
