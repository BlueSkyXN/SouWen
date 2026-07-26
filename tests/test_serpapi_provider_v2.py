from __future__ import annotations

import pytest

from souwen.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchRequest,
)
from souwen.providers.information_sources.serpapi import (
    SERPAPI_PROVIDER_MANIFEST,
    SERPAPI_PROVIDER_SPEC,
    SerpApiSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_serpapi_manifest_and_spec_agree() -> None:
    assert SERPAPI_PROVIDER_SPEC.auth.reference == "SERPAPI_API_KEY"
    assert SERPAPI_PROVIDER_SPEC.auth.required is True
    assert SERPAPI_PROVIDER_MANIFEST.id == "serpapi"
    assert SERPAPI_PROVIDER_SPEC.transport.host == "serpapi.com"


@pytest.mark.asyncio
async def test_serpapi_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="serpapi",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="serpapi",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="serpapi",
            )
        ],
    )
    client = _Client(response)
    page = await SerpApiSearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="serpapi"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await SerpApiSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="serpapi-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
