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
from souwen.providers.information_sources.aliyun_iqs import (
    ALIYUN_IQS_PROVIDER_MANIFEST,
    ALIYUN_IQS_PROVIDER_SPEC,
    AliyunIQSSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_aliyun_iqs_manifest_and_spec_agree() -> None:
    assert ALIYUN_IQS_PROVIDER_SPEC.auth.reference == "ALIYUN_IQS_API_KEY"
    assert ALIYUN_IQS_PROVIDER_SPEC.auth.required is True
    assert ALIYUN_IQS_PROVIDER_MANIFEST.id == "aliyun_iqs"
    assert ALIYUN_IQS_PROVIDER_SPEC.transport.host == "cloud-iqs.aliyuncs.com"


@pytest.mark.asyncio
async def test_aliyun_iqs_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="aliyun_iqs",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="aliyun_iqs",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="aliyun_iqs",
            )
        ],
    )
    client = _Client(response)
    page = await AliyunIQSSearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="aliyun_iqs"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await AliyunIQSSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="aliyun_iqs-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
