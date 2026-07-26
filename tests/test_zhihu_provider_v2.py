from __future__ import annotations
import pytest
from souwen.providers.runtime_clients.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.zhihu import (
    ZHIHU_PROVIDER_MANIFEST,
    ZHIHU_PROVIDER_SPEC,
    ZhihuSearchProvider,
)


class _Client:
    def __init__(self):
        self.called = False

    async def search(self, query, max_results=10):
        self.called = True
        return SearchResponse(
            query=query,
            source="zhihu",
            total_results=1,
            results=[
                WebSearchResult(
                    source="zhihu",
                    title="Answer",
                    url="https://www.zhihu.com/question/1",
                    snippet="text",
                    engine="zhihu",
                )
            ],
        )


@pytest.mark.asyncio
async def test_zhihu_rejects_limit_above_single_page_contract():
    client = _Client()
    provider = ZhihuSearchProvider(client)
    with pytest.raises(ProviderError) as caught:
        await provider.search(
            SearchRequest(query="topic", domains=("social",), page=SearchPageRequest(limit=21)),
            RequestContext(request_id="zhihu"),
            ExecutionContext.with_timeout(1),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert client.called is False
    assert ZHIHU_PROVIDER_MANIFEST.network.egress_hosts == ("www.zhihu.com",)
    assert ZHIHU_PROVIDER_SPEC.transport.operations[0].endpoint == "/api/v4/search_v3"
