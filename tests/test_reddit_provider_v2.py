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
from souwen.providers.information_sources.reddit import (
    REDDIT_PROVIDER_MANIFEST,
    REDDIT_PROVIDER_SPEC,
    RedditSearchProvider,
)
from souwen.platform.provider_spec import validate_spec_manifest


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_reddit_manifest_and_spec_agree() -> None:
    assert REDDIT_PROVIDER_SPEC.auth.reference == "REDDIT_CLIENT_ID"
    assert REDDIT_PROVIDER_SPEC.auth.required is False
    assert REDDIT_PROVIDER_MANIFEST.id == "reddit"
    assert REDDIT_PROVIDER_SPEC.transport.host == "www.reddit.com"
    assert REDDIT_PROVIDER_SPEC.hosts == ("www.reddit.com", "oauth.reddit.com")
    assert set(REDDIT_PROVIDER_MANIFEST.network.egress_hosts) == {
        "www.reddit.com",
        "oauth.reddit.com",
    }
    assert {operation.endpoint for operation in REDDIT_PROVIDER_SPEC.transport.operations} == {
        "/search.json",
        "/api/v1/access_token",
    }
    assert REDDIT_PROVIDER_SPEC.additional_transports[0].operations[0].endpoint == "/search"
    with pytest.raises(ValueError, match="hosts do not match"):
        validate_spec_manifest(
            REDDIT_PROVIDER_SPEC.model_copy(update={"additional_transports": ()}),
            REDDIT_PROVIDER_MANIFEST,
        )


@pytest.mark.asyncio
async def test_reddit_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="reddit",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="reddit",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="reddit",
            )
        ],
    )
    client = _Client(response)
    page = await RedditSearchProvider(client).search(
        SearchRequest(query="query", domains=("social",)),
        RequestContext(request_id="reddit"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await RedditSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("social",)),
            RequestContext(request_id="reddit-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
