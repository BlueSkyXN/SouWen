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
from souwen.providers.information_sources.facebook import (
    FACEBOOK_PROVIDER_MANIFEST,
    FACEBOOK_PROVIDER_SPEC,
    FacebookSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_facebook_manifest_and_spec_agree() -> None:
    assert FACEBOOK_PROVIDER_SPEC.auth.reference == "FACEBOOK_APP_ID"
    assert FACEBOOK_PROVIDER_SPEC.auth.required is True
    assert FACEBOOK_PROVIDER_SPEC.auth.placement == "bearer"
    assert FACEBOOK_PROVIDER_SPEC.auth_reference_requirements == (
        ("FACEBOOK_APP_ID", True),
        ("FACEBOOK_APP_SECRET", True),
    )
    assert FACEBOOK_PROVIDER_SPEC.transport.operations[0].endpoint == "/v19.0/pages/search"
    assert FACEBOOK_PROVIDER_MANIFEST.id == "facebook"
    assert FACEBOOK_PROVIDER_SPEC.transport.host == "graph.facebook.com"


@pytest.mark.asyncio
async def test_facebook_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="facebook",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="facebook",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="facebook",
            )
        ],
    )
    client = _Client(response)
    page = await FacebookSearchProvider(client).search(
        SearchRequest(query="query", domains=("social",)),
        RequestContext(request_id="facebook"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await FacebookSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("social",)),
            RequestContext(request_id="facebook-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
