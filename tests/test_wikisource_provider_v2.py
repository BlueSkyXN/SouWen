from __future__ import annotations
import pytest
from souwen.providers.runtime_clients.models import BookResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.wikisource import (
    WIKISOURCE_PROVIDER_MANIFEST,
    WIKISOURCE_PROVIDER_SPEC,
    WikisourceSearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(self, query: str, per_page: int = 10, page: int = 1, language: str = "zh"):
        self.calls.append((query, per_page, page, language))
        return self.response


@pytest.mark.asyncio
async def test_wikisource_search_forces_zh_allowlisted_host_default() -> None:
    client = _Client(
        SearchResponse(
            query="catalog",
            source="wikisource",
            total_results=None,
            per_page=10,
            results=[
                BookResult(
                    source="wikisource",
                    source_record_id="zh:1",
                    title="Catalog",
                    languages=["zh"],
                    source_url="https://zh.wikisource.org/wiki/Catalog",
                )
            ],
        )
    )
    page = await WikisourceSearchProvider(client).search(
        SearchRequest(query="catalog", domains=("book",)),
        RequestContext(request_id="wikisource"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("catalog", 10, 1, "zh")]
    assert page.items[0].attributes.language == "zh"
    assert WIKISOURCE_PROVIDER_MANIFEST.network.egress_hosts == ("zh.wikisource.org",)
    assert WIKISOURCE_PROVIDER_SPEC.hosts == ("zh.wikisource.org",)
