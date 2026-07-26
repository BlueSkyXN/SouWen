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
from souwen.providers.information_sources.linkup import (
    LINKUP_PROVIDER_MANIFEST,
    LINKUP_PROVIDER_SPEC,
    LinkupSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_linkup_manifest_and_spec_agree() -> None:
    assert LINKUP_PROVIDER_SPEC.auth.reference == "LINKUP_API_KEY"
    assert LINKUP_PROVIDER_SPEC.auth.required is True
    assert LINKUP_PROVIDER_MANIFEST.id == "linkup"
    assert LINKUP_PROVIDER_SPEC.transport.host == "api.linkup.so"


@pytest.mark.asyncio
async def test_linkup_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="linkup",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="linkup",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="linkup",
            )
        ],
    )
    client = _Client(response)
    page = await LinkupSearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="linkup"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await LinkupSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="linkup-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
