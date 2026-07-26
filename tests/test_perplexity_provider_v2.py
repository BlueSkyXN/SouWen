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
from souwen.providers.information_sources.perplexity import (
    PERPLEXITY_PROVIDER_MANIFEST,
    PERPLEXITY_PROVIDER_SPEC,
    PerplexitySearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_perplexity_manifest_and_spec_agree() -> None:
    assert PERPLEXITY_PROVIDER_SPEC.auth.reference == "PERPLEXITY_API_KEY"
    assert PERPLEXITY_PROVIDER_SPEC.auth.required is True
    assert PERPLEXITY_PROVIDER_MANIFEST.id == "perplexity"
    assert PERPLEXITY_PROVIDER_SPEC.transport.host == "api.perplexity.ai"


@pytest.mark.asyncio
async def test_perplexity_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="perplexity",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="perplexity",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="perplexity",
            )
        ],
    )
    client = _Client(response)
    page = await PerplexitySearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="perplexity"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await PerplexitySearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="perplexity-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
