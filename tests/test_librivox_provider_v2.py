from __future__ import annotations
import pytest
from souwen.models import BookResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.librivox import (
    LIBRIVOX_PROVIDER_MANIFEST,
    LIBRIVOX_PROVIDER_SPEC,
    LibriVoxSearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(
        self, query: str, per_page: int = 10, page: int = 1, *, search_field: str = "title"
    ):
        self.calls.append((query, per_page, page, search_field))
        return self.response


@pytest.mark.asyncio
async def test_librivox_search_preserves_default_title_search() -> None:
    client = _Client(
        SearchResponse(
            query="catalog",
            source="librivox",
            total_results=None,
            per_page=10,
            results=[
                BookResult(
                    source="librivox",
                    source_record_id="7",
                    title="Catalog",
                    source_url="https://librivox.org/audiobook/7",
                )
            ],
        )
    )
    page = await LibriVoxSearchProvider(client).search(
        SearchRequest(query="catalog", domains=("book",)),
        RequestContext(request_id="librivox"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("catalog", 10, 1, "title")]
    assert page.items[0].attributes.resource_type == "book"
    assert LIBRIVOX_PROVIDER_MANIFEST.network.proxy_supported is True
    assert LIBRIVOX_PROVIDER_SPEC.transport.host == "librivox.org"
