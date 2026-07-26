from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchRequest,
)
from souwen.providers.information_sources.wikipedia import (
    WIKIPEDIA_PROVIDER_MANIFEST,
    WIKIPEDIA_PROVIDER_SPEC,
    WikipediaSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_wikipedia_manifest_and_spec_agree() -> None:
    assert WIKIPEDIA_PROVIDER_SPEC.auth.reference is None
    assert WIKIPEDIA_PROVIDER_MANIFEST.id == "wikipedia"
    assert WIKIPEDIA_PROVIDER_SPEC.transport.host == "zh.wikipedia.org"


@pytest.mark.asyncio
async def test_wikipedia_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="wikipedia",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="wikipedia",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="wikipedia",
            )
        ],
    )
    client = _Client(response)
    page = await WikipediaSearchProvider(client).search(
        SearchRequest(query="query", domains=("knowledge",)),
        RequestContext(request_id="wikipedia"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await WikipediaSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("knowledge",)),
            RequestContext(request_id="wikipedia-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
