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
from souwen.providers.information_sources.brave_api import (
    BRAVE_API_PROVIDER_MANIFEST,
    BRAVE_API_PROVIDER_SPEC,
    BraveApiSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_brave_api_manifest_and_spec_agree() -> None:
    assert BRAVE_API_PROVIDER_SPEC.auth.reference == "BRAVE_API_KEY"
    assert BRAVE_API_PROVIDER_SPEC.auth.required is True
    assert BRAVE_API_PROVIDER_MANIFEST.id == "brave_api"
    assert BRAVE_API_PROVIDER_SPEC.transport.host == "api.search.brave.com"


@pytest.mark.asyncio
async def test_brave_api_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="brave_api",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="brave_api",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="brave_api",
            )
        ],
    )
    client = _Client(response)
    page = await BraveApiSearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="brave_api"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await BraveApiSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="brave_api-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
