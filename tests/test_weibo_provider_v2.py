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
from souwen.providers.information_sources.weibo import (
    WEIBO_PROVIDER_MANIFEST,
    WEIBO_PROVIDER_SPEC,
    WeiboSearchProvider,
)


class _Client:
    def __init__(self):
        self.called = False

    async def search(self, query, max_results=10):
        self.called = True
        return SearchResponse(
            query=query,
            source="weibo",
            total_results=1,
            results=[
                WebSearchResult(
                    source="weibo",
                    title="Post",
                    url="https://m.weibo.cn/detail/1",
                    snippet="text",
                    engine="weibo",
                )
            ],
        )


@pytest.mark.asyncio
async def test_weibo_rejects_limit_above_single_page_contract():
    client = _Client()
    provider = WeiboSearchProvider(client)
    with pytest.raises(ProviderError) as caught:
        await provider.search(
            SearchRequest(query="topic", domains=("social",), page=SearchPageRequest(limit=11)),
            RequestContext(request_id="weibo"),
            ExecutionContext.with_timeout(1),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert client.called is False
    assert WEIBO_PROVIDER_MANIFEST.network.egress_hosts == ("m.weibo.cn",)
    assert WEIBO_PROVIDER_SPEC.transport.operations[0].endpoint == "/api/container/getIndex"
