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
from souwen.providers.information_sources.scrapingdog import (
    SCRAPINGDOG_PROVIDER_MANIFEST,
    SCRAPINGDOG_PROVIDER_SPEC,
    ScrapingDogSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_scrapingdog_manifest_and_spec_agree() -> None:
    assert SCRAPINGDOG_PROVIDER_SPEC.auth.reference == "SCRAPINGDOG_API_KEY"
    assert SCRAPINGDOG_PROVIDER_SPEC.auth.required is True
    assert SCRAPINGDOG_PROVIDER_MANIFEST.id == "scrapingdog"
    assert SCRAPINGDOG_PROVIDER_SPEC.transport.host == "api.scrapingdog.com"


@pytest.mark.asyncio
async def test_scrapingdog_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="scrapingdog",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="scrapingdog",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="scrapingdog",
            )
        ],
    )
    client = _Client(response)
    page = await ScrapingDogSearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="scrapingdog"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await ScrapingDogSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="scrapingdog-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
