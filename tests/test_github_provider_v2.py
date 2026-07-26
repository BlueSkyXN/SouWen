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
from souwen.providers.information_sources.github import (
    GITHUB_PROVIDER_MANIFEST,
    GITHUB_PROVIDER_SPEC,
    GitHubSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_github_manifest_and_spec_agree() -> None:
    assert GITHUB_PROVIDER_SPEC.auth.reference == "GITHUB_TOKEN"
    assert GITHUB_PROVIDER_SPEC.auth.required is False
    assert GITHUB_PROVIDER_MANIFEST.id == "github"
    assert GITHUB_PROVIDER_SPEC.transport.host == "api.github.com"


@pytest.mark.asyncio
async def test_github_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="github",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="github",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="github",
            )
        ],
    )
    client = _Client(response)
    page = await GitHubSearchProvider(client).search(
        SearchRequest(query="query", domains=("developer",)),
        RequestContext(request_id="github"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await GitHubSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("developer",)),
            RequestContext(request_id="github-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
