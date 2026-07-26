from __future__ import annotations
import pytest
from souwen.models import BookResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.doab import (
    DOAB_PROVIDER_MANIFEST,
    DOAB_PROVIDER_SPEC,
    DOABSearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(self, query: str, per_page: int = 10, page: int = 1):
        self.calls.append((query, per_page, page))
        return self.response


@pytest.mark.asyncio
async def test_doab_search_keeps_bounded_first_page_only() -> None:
    client = _Client(
        SearchResponse(
            query="catalog",
            source="doab",
            total_results=None,
            per_page=10,
            results=[
                BookResult(
                    source="doab",
                    source_record_id="20.500.12854/1",
                    title="Catalog",
                    source_url="https://directory.doabooks.org/handle/20.500.12854/1",
                )
            ],
        )
    )
    page = await DOABSearchProvider(client).search(
        SearchRequest(query="catalog", domains=("book",)),
        RequestContext(request_id="doab"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("catalog", 10, 1)]
    assert page.page.total is None
    assert DOAB_PROVIDER_MANIFEST.network.proxy_supported is True
    assert DOAB_PROVIDER_SPEC.transport.operations[0].endpoint == "/oai/request"
