from __future__ import annotations
import pytest
from souwen.models import PaperResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.europepmc import EuropePmcSearchProvider


class Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, query, page_size=10):
        self.calls.append((query, page_size))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def paper(**kw):
    d = {
        "source": "europepmc",
        "title": "Paper",
        "source_url": "https://europepmc.org/article/MED/123",
        "raw": {"id": "123", "is_open_access": True},
    }
    d.update(kw)
    return PaperResult(**d)


def response(*items, limit=2):
    return SearchResponse(
        query="q",
        source="europepmc",
        total_results=len(items),
        page=1,
        per_page=limit,
        results=list(items),
    )


@pytest.mark.asyncio
async def test_bridge_success_empty_config_and_identifier():
    req = SearchRequest(query="q", domains=("paper",), page=SearchPageRequest(limit=2))
    ctx = RequestContext(request_id="epmc")
    c = Client(response(paper()))
    page = await EuropePmcSearchProvider(c).search(req, ctx, ExecutionContext.with_timeout(1))
    assert c.calls == [("q", 2)] and page.items[0].id == "europepmc:123"
    assert (
        await EuropePmcSearchProvider(Client(response())).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    ).items == ()
    with pytest.raises(ProviderError) as off:
        await EuropePmcSearchProvider(Client(response()), enabled=False).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert off.value.code is ProviderErrorCode.INVALID_CONFIG
    with pytest.raises(ProviderError) as bad:
        await EuropePmcSearchProvider(Client(response(paper(raw={})))).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert bad.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
    with pytest.raises(ProviderError) as error:
        await EuropePmcSearchProvider(Client(RuntimeError("token=fixture-secret"))).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert error.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert "fixture-secret" not in str(error.value)
