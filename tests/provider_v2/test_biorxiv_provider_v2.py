from __future__ import annotations
import pytest
from souwen.models import Author, PaperResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.biorxiv import BioRxivSearchProvider


class Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, query, per_page=10):
        self.calls.append((query, per_page))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def paper(**kw):
    d = {
        "source": "biorxiv",
        "title": "Paper",
        "authors": [Author(name="Ada")],
        "doi": "10.1101/2025.12345",
        "source_url": "https://doi.org/10.1101/2025.12345",
        "raw": {},
    }
    d.update(kw)
    return PaperResult(**d)


def response(*items, limit=2):
    return SearchResponse(
        query="q",
        source="biorxiv",
        total_results=len(items),
        page=1,
        per_page=limit,
        results=list(items),
    )


@pytest.mark.asyncio
async def test_bridge_success_empty_config_and_identifier():
    req = SearchRequest(query="q", domains=("paper",), page=SearchPageRequest(limit=2))
    ctx = RequestContext(request_id="bio")
    c = Client(response(paper()))
    page = await BioRxivSearchProvider(c).search(req, ctx, ExecutionContext.with_timeout(1))
    assert c.calls == [("q", 2)] and page.items[0].id == "doi:10.1101/2025.12345"
    assert (
        await BioRxivSearchProvider(Client(response())).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    ).items == ()
    with pytest.raises(ProviderError) as off:
        await BioRxivSearchProvider(Client(response()), enabled=False).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert off.value.code is ProviderErrorCode.INVALID_CONFIG
    with pytest.raises(ProviderError) as bad:
        await BioRxivSearchProvider(
            Client(response(paper(doi=None, source_url="https://www.biorxiv.org/")))
        ).search(req, ctx, ExecutionContext.with_timeout(1))
    assert bad.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
    with pytest.raises(ProviderError) as error:
        await BioRxivSearchProvider(Client(RuntimeError("token=fixture-secret"))).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert error.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert "fixture-secret" not in str(error.value)
