from __future__ import annotations
import pytest
from souwen.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.coolapk import (
    COOLAPK_PROVIDER_MANIFEST,
    COOLAPK_PROVIDER_SPEC,
    CoolapkSearchProvider,
)


class _Client:
    def __init__(self, response):
        self.response, self.calls = response, []

    async def search(self, query, max_results=20):
        self.calls.append((query, max_results))
        return self.response


def _request(limit=3):
    return SearchRequest(query="android", domains=("cn_tech",), page=SearchPageRequest(limit=limit))


@pytest.mark.asyncio
async def test_coolapk_projects_only_its_reviewed_result_domain():
    client = _Client(
        SearchResponse(
            query="android",
            source="coolapk",
            total_results=1,
            results=[
                WebSearchResult(
                    source="coolapk",
                    title="App",
                    url="https://www.coolapk.com/feed/1#fragment",
                    snippet="text",
                    engine="coolapk",
                    raw={"secret": "never-export"},
                )
            ],
        )
    )
    page = await CoolapkSearchProvider(client).search(
        _request(), RequestContext(request_id="coolapk"), ExecutionContext.with_timeout(1)
    )
    assert client.calls == [("android", 3)]
    assert str(page.items[0].url) == "https://www.coolapk.com/feed/1"
    assert "raw" not in page.items[0].model_dump()
    assert COOLAPK_PROVIDER_MANIFEST.network.egress_hosts == ("html.duckduckgo.com",)
    assert COOLAPK_PROVIDER_SPEC.transport.operations[0].endpoint == "/html/"


@pytest.mark.asyncio
async def test_coolapk_rejects_ddg_result_outside_target_domain():
    client = _Client(
        SearchResponse(
            query="android",
            source="coolapk",
            results=[
                WebSearchResult(
                    source="coolapk", title="Wrong", url="https://example.test/1", engine="coolapk"
                )
            ],
        )
    )
    with pytest.raises(ProviderError) as caught:
        await CoolapkSearchProvider(client).search(
            _request(), RequestContext(request_id="bad"), ExecutionContext.with_timeout(1)
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
