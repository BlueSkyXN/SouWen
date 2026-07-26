from __future__ import annotations

import pytest

from souwen.models import Author, PaperResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.pmc import (
    PMC_BRIDGE_SPEC,
    PMC_PROVIDER_MANIFEST,
    PmcSearchProvider,
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
async def test_pmc_bridge_keeps_two_step_xml_result_identity() -> None:
    response = SearchResponse(
        query="cancer",
        source="pmc",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            PaperResult(
                source="pmc",
                title="PMC",
                authors=[Author(name="Ada")],
                year=2024,
                source_url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/",
                raw={"pmcid": "PMC123"},
            )
        ],
    )
    client = _Client(response)
    page = await PmcSearchProvider(client).search(
        SearchRequest(query="cancer", domains=("paper",)),
        RequestContext(request_id="pmc"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("cancer", 10, 0)]
    assert page.items[0].id == "pmc:PMC123" and page.items[0].attributes.open_access is True
    assert PMC_BRIDGE_SPEC.transport.protocol == "multi_step_xml"
    assert PMC_PROVIDER_MANIFEST.secrets.references == ()
    assert PMC_PROVIDER_MANIFEST.secrets.optional_references == ("PUBMED_API_KEY",)
