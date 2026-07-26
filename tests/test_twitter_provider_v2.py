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
from souwen.providers.information_sources.twitter import (
    TWITTER_PROVIDER_MANIFEST,
    TWITTER_PROVIDER_SPEC,
    TwitterSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_twitter_manifest_and_spec_agree() -> None:
    assert TWITTER_PROVIDER_SPEC.auth.reference == "TWITTER_BEARER_TOKEN"
    assert TWITTER_PROVIDER_SPEC.auth.required is True
    assert TWITTER_PROVIDER_MANIFEST.id == "twitter"
    assert TWITTER_PROVIDER_SPEC.transport.host == "api.twitter.com"


@pytest.mark.asyncio
async def test_twitter_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="twitter",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="twitter",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="twitter",
            )
        ],
    )
    client = _Client(response)
    page = await TwitterSearchProvider(client).search(
        SearchRequest(query="query", domains=("social",)),
        RequestContext(request_id="twitter"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await TwitterSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("social",)),
            RequestContext(request_id="twitter-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
