from __future__ import annotations

import pytest

from souwen.models import Author, PaperResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.pubmed import (
    PUBMED_BRIDGE_SPEC,
    PUBMED_PROVIDER_MANIFEST,
    PubMedSearchProvider,
)


class _Client:
    def __init__(self, response):
        self.response, self.calls = response, []

    async def search(self, query, retmax=10, retstart=0):
        self.calls.append((query, retmax, retstart))
        return self.response

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_pubmed_bridge_keeps_two_step_xml_result_identity() -> None:
    response = SearchResponse(
        query="cancer",
        source="pubmed",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PaperResult(
                source="pubmed",
                title="PubMed",
                authors=[Author(name="Ada")],
                year=2024,
                doi="10.1000/test",
                source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
                raw={"pmid": "123"},
            )
        ],
    )
    client = _Client(response)
    page = await PubMedSearchProvider(client).search(
        SearchRequest(query="cancer", domains=("paper",)),
        RequestContext(request_id="pubmed"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("cancer", 10, 0)]
    assert page.items[0].id == "pmid:123"
    assert PUBMED_BRIDGE_SPEC.transport.protocol == "multi_step_xml"
    assert PUBMED_PROVIDER_MANIFEST.secrets.references == ()
    assert PUBMED_PROVIDER_MANIFEST.secrets.optional_references == ("PUBMED_API_KEY",)
