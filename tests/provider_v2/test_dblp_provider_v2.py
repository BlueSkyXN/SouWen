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
from souwen.providers.information_sources.dblp import DblpSearchProvider


class Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, query, hits=10, first=0):
        self.calls.append((query, hits, first))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def paper(**kw):
    d = {
        "source": "dblp",
        "title": "Paper",
        "doi": "10.1234/test",
        "source_url": "https://dblp.org/rec/test",
        "raw": {},
    }
    d.update(kw)
    return PaperResult(**d)


def response(*items, limit=2):
    return SearchResponse(
        query="q",
        source="dblp",
        total_results=len(items),
        page=1,
        per_page=limit,
        results=list(items),
    )


@pytest.mark.asyncio
async def test_bridge_success_empty_config_and_identifier():
    req = SearchRequest(query="q", domains=("paper",), page=SearchPageRequest(limit=2))
    ctx = RequestContext(request_id="dblp")
    c = Client(response(paper()))
    page = await DblpSearchProvider(c).search(req, ctx, ExecutionContext.with_timeout(1))
    assert c.calls == [("q", 2, 0)] and page.items[0].id == "doi:10.1234/test"
    assert (
        await DblpSearchProvider(Client(response())).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    ).items == ()
    with pytest.raises(ProviderError) as off:
        await DblpSearchProvider(Client(response()), enabled=False).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert off.value.code is ProviderErrorCode.INVALID_CONFIG
    with pytest.raises(ProviderError) as bad:
        await DblpSearchProvider(Client(response(paper(doi=None)))).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert bad.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
    with pytest.raises(ProviderError) as error:
        await DblpSearchProvider(Client(RuntimeError("token=fixture-secret"))).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert error.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert "fixture-secret" not in str(error.value)
