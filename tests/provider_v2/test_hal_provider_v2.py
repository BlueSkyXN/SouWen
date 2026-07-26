from __future__ import annotations
import pytest
from souwen.providers.runtime_clients.models import PaperResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.hal import HalSearchProvider


class Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, query, rows=10):
        self.calls.append((query, rows))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def paper(**kw):
    d = {
        "source": "hal",
        "title": "Paper",
        "source_url": "https://hal.science/hal-123",
        "raw": {"hal_id": "hal-123", "doc_type": "ART"},
    }
    d.update(kw)
    return PaperResult(**d)


def response(*items, limit=2):
    return SearchResponse(
        query="q",
        source="hal",
        total_results=len(items),
        page=1,
        per_page=limit,
        results=list(items),
    )


@pytest.mark.asyncio
async def test_bridge_success_empty_config_and_identifier():
    req = SearchRequest(query="q", domains=("paper",), page=SearchPageRequest(limit=2))
    ctx = RequestContext(request_id="hal")
    c = Client(response(paper()))
    page = await HalSearchProvider(c).search(req, ctx, ExecutionContext.with_timeout(1))
    assert c.calls == [("q", 2)] and page.items[0].id == "hal:hal-123"
    assert (
        await HalSearchProvider(Client(response())).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    ).items == ()
    with pytest.raises(ProviderError) as off:
        await HalSearchProvider(Client(response()), enabled=False).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert off.value.code is ProviderErrorCode.INVALID_CONFIG
    with pytest.raises(ProviderError) as bad:
        await HalSearchProvider(Client(response(paper(raw={})))).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert bad.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
    with pytest.raises(ProviderError) as error:
        await HalSearchProvider(Client(RuntimeError("token=fixture-secret"))).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert error.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert "fixture-secret" not in str(error.value)
