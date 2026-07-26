from __future__ import annotations
import pytest
from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.providers.information_sources.arxiv import ArxivSearchProvider


class Client:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def search(self, query, max_results=10):
        self.calls.append((query, max_results))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def paper(**kw):
    d = {
        "source": "arxiv",
        "title": "Paper",
        "authors": [Author(name="Ada")],
        "source_url": "http://arxiv.org/abs/2501.12345",
        "raw": {},
    }
    d.update(kw)
    return PaperResult(**d)


def response(*items, limit=2):
    return SearchResponse(
        query="q",
        source="arxiv",
        total_results=len(items),
        page=1,
        per_page=limit,
        results=list(items),
    )


@pytest.mark.asyncio
async def test_bridge_success_empty_config_error_and_identifier():
    req = SearchRequest(query="q", domains=("paper",), page=SearchPageRequest(limit=2))
    ctx = RequestContext(request_id="arxiv")
    c = Client(response(paper()))
    page = await ArxivSearchProvider(c).search(req, ctx, ExecutionContext.with_timeout(1))
    assert c.calls == [("q", 2)] and page.items[0].id == "arxiv:2501.12345"
    legacy = await ArxivSearchProvider(
        Client(response(paper(source_url="https://arxiv.org/abs/hep-th/9901001v2")))
    ).search(req, ctx, ExecutionContext.with_timeout(1))
    assert legacy.items[0].id == "arxiv:hep-th/9901001v2"
    assert (
        await ArxivSearchProvider(Client(response())).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    ).items == ()
    with pytest.raises(ProviderError) as off:
        await ArxivSearchProvider(Client(response()), enabled=False).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert off.value.code is ProviderErrorCode.INVALID_CONFIG
    with pytest.raises(ProviderError) as bad:
        await ArxivSearchProvider(
            Client(response(paper(source_url="https://example.test/x")))
        ).search(req, ctx, ExecutionContext.with_timeout(1))
    assert bad.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
    with pytest.raises(ProviderError) as error:
        await ArxivSearchProvider(Client(RuntimeError("token=fixture-secret"))).search(
            req, ctx, ExecutionContext.with_timeout(1)
        )
    assert (
        error.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
        and "fixture-secret" not in str(error.value)
    )
