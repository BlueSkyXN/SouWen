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
from souwen.providers.information_sources.serper import (
    SERPER_PROVIDER_MANIFEST,
    SERPER_PROVIDER_SPEC,
    SerperSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_serper_manifest_and_spec_agree() -> None:
    assert SERPER_PROVIDER_SPEC.auth.reference == "SERPER_API_KEY"
    assert SERPER_PROVIDER_SPEC.auth.required is True
    assert SERPER_PROVIDER_MANIFEST.id == "serper"
    assert SERPER_PROVIDER_SPEC.transport.host == "google.serper.dev"


@pytest.mark.asyncio
async def test_serper_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="serper",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="serper",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="serper",
            )
        ],
    )
    client = _Client(response)
    page = await SerperSearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="serper"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await SerperSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="serper-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
