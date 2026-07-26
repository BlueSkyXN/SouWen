from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.osti import (
    OSTI_BRIDGE_SPEC,
    OSTI_PROVIDER_MANIFEST,
    OstiSearchProvider,
)


class _Client:
    def __init__(self, response):
        self.response, self.calls = response, []

    async def search(self, query, rows=10, page=1):
        self.calls.append((query, rows, page))
        return self.response

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_osti_bridge_keeps_header_derived_total_and_numeric_identity() -> None:
    response = SearchResponse(
        query="energy",
        source="osti",
        total_results=2,
        page=1,
        per_page=10,
        results=[
            PaperResult(
                source="osti",
                title="Energy",
                authors=[Author(name="Ada")],
                year=2024,
                source_url="https://www.osti.gov/biblio/3012392",
                raw={"osti_id": "3012392", "product_type": "Report"},
            )
        ],
    )
    client = _Client(response)
    page = await OstiSearchProvider(client).search(
        SearchRequest(query="energy", domains=("paper",)),
        RequestContext(request_id="osti"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("energy", 10, 1)]
    assert page.page.total == 2 and page.items[0].id == "osti:3012392"
    assert OSTI_BRIDGE_SPEC.transport.protocol == "json"
    assert OSTI_PROVIDER_MANIFEST.secrets.references == ()
