from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.iacr import (
    IACR_BRIDGE_SPEC,
    IACR_PROVIDER_MANIFEST,
    IacrSearchProvider,
)


class _Client:
    def __init__(self, response):
        self.response = response

    async def search(self, query, max_results=10):
        assert (query, max_results) == ("crypto", 10)
        return self.response

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_iacr_bridge_preserves_html_derived_paper_identity() -> None:
    response = SearchResponse(
        query="crypto",
        source="iacr",
        total_results=1,
        results=[
            PaperResult(
                source="iacr",
                title="Crypto",
                authors=[Author(name="Ada")],
                year=2024,
                abstract="Fixture",
                source_url="https://eprint.iacr.org/2024/1",
                raw={"paper_id": "2024/1"},
            )
        ],
    )
    page = await IacrSearchProvider(_Client(response)).search(
        SearchRequest(query="crypto", domains=("paper",)),
        RequestContext(request_id="iacr"),
        ExecutionContext.with_timeout(5),
    )
    assert page.items[0].id == "iacr:2024/1"
    assert IACR_BRIDGE_SPEC.transport.protocol == "html"
    assert IACR_PROVIDER_MANIFEST.secrets.references == ()
