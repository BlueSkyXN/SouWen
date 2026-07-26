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
from souwen.providers.information_sources.zhipuai import (
    ZHIPUAI_PROVIDER_MANIFEST,
    ZHIPUAI_PROVIDER_SPEC,
    ZhipuAISearchSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_zhipuai_manifest_and_spec_agree() -> None:
    assert ZHIPUAI_PROVIDER_SPEC.auth.reference == "ZHIPUAI_API_KEY"
    assert ZHIPUAI_PROVIDER_SPEC.auth.required is True
    assert ZHIPUAI_PROVIDER_MANIFEST.id == "zhipuai"
    assert ZHIPUAI_PROVIDER_SPEC.transport.host == "open.bigmodel.cn"


@pytest.mark.asyncio
async def test_zhipuai_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="zhipuai",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="zhipuai",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="zhipuai",
            )
        ],
    )
    client = _Client(response)
    page = await ZhipuAISearchSearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="zhipuai"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await ZhipuAISearchSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="zhipuai-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
