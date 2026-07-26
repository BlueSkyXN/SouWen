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
from souwen.providers.information_sources.linuxdo import (
    LINUXDO_PROVIDER_MANIFEST,
    LINUXDO_PROVIDER_SPEC,
    LinuxDoSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_linuxdo_manifest_and_spec_agree() -> None:
    assert LINUXDO_PROVIDER_SPEC.auth.reference is None
    assert LINUXDO_PROVIDER_MANIFEST.id == "linuxdo"
    assert LINUXDO_PROVIDER_SPEC.transport.host == "linux.do"


@pytest.mark.asyncio
async def test_linuxdo_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="linuxdo",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="linuxdo",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="linuxdo",
            )
        ],
    )
    client = _Client(response)
    page = await LinuxDoSearchProvider(client).search(
        SearchRequest(query="query", domains=("cn_tech",)),
        RequestContext(request_id="linuxdo"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await LinuxDoSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("cn_tech",)),
            RequestContext(request_id="linuxdo-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
