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
from souwen.providers.information_sources.feishu_drive import (
    FEISHU_DRIVE_PROVIDER_MANIFEST,
    FEISHU_DRIVE_PROVIDER_SPEC,
    FeishuDriveSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_feishu_drive_manifest_and_spec_agree() -> None:
    assert FEISHU_DRIVE_PROVIDER_SPEC.auth.reference == "FEISHU_APP_ID"
    assert FEISHU_DRIVE_PROVIDER_SPEC.auth.required is True
    assert FEISHU_DRIVE_PROVIDER_MANIFEST.id == "feishu_drive"
    assert FEISHU_DRIVE_PROVIDER_SPEC.transport.host == "open.feishu.cn"
    assert {
        operation.endpoint for operation in FEISHU_DRIVE_PROVIDER_SPEC.transport.operations
    } == {
        "/open-apis/auth/v3/tenant_access_token/internal",
        "/open-apis/suite/docs-api/search/object",
    }


@pytest.mark.asyncio
async def test_feishu_drive_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="feishu_drive",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="feishu_drive",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="feishu_drive",
            )
        ],
    )
    client = _Client(response)
    page = await FeishuDriveSearchProvider(client).search(
        SearchRequest(query="query", domains=("office",)),
        RequestContext(request_id="feishu_drive"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await FeishuDriveSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("office",)),
            RequestContext(request_id="feishu_drive-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
