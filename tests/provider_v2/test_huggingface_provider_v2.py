"""Deterministic Provider v2 checks for HuggingFace Papers."""

from __future__ import annotations
import asyncio
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
from souwen.providers.information_sources.huggingface import HuggingFaceSearchProvider


class Client:
    def __init__(self, response):
        self.response, self.calls, self.closed = response, [], 0

    async def search(self, query, top_n=10):
        self.calls.append((query, top_n))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def close(self):
        self.closed += 1


def response(*items, limit=10):
    return SearchResponse(
        query="q",
        source="huggingface",
        total_results=len(items),
        page=1,
        per_page=limit,
        results=list(items),
    )


def item(**overrides):
    values = {
        "source": "huggingface",
        "title": "Paper",
        "authors": [Author(name="Ada")],
        "abstract": "Summary",
        "year": 2025,
        "source_url": "https://huggingface.co/papers/2501.12345",
        "raw": {"arxiv_id": "2501.12345"},
    }
    values.update(overrides)
    return PaperResult(**values)


def request(**overrides):
    values = {"query": "q", "domains": ("paper",), "page": SearchPageRequest(limit=3)}
    values.update(overrides)
    return SearchRequest(**values)


@pytest.mark.asyncio
async def test_success_empty_disabled_error_and_identifier_boundaries():
    client = Client(response(item(), limit=3))
    provider = HuggingFaceSearchProvider(client)
    page = await provider.search(
        request(), RequestContext(request_id="hf"), ExecutionContext.with_timeout(1)
    )
    assert client.calls == [("q", 3)] and page.items[0].id == "huggingface:2501.12345"
    assert (
        await HuggingFaceSearchProvider(Client(response(limit=3))).search(
            request(), RequestContext(request_id="empty"), ExecutionContext.with_timeout(1)
        )
    ).items == ()
    with pytest.raises(ProviderError) as disabled:
        await HuggingFaceSearchProvider(Client(response()), enabled=False).search(
            request(), RequestContext(request_id="off"), ExecutionContext.with_timeout(1)
        )
    assert disabled.value.code is ProviderErrorCode.INVALID_CONFIG
    with pytest.raises(ProviderError) as invalid:
        await HuggingFaceSearchProvider(Client(response(item(raw={}), limit=3))).search(
            request(), RequestContext(request_id="bad"), ExecutionContext.with_timeout(1)
        )
    assert invalid.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
    event = asyncio.Event()
    event.set()
    with pytest.raises(ProviderError) as cancelled:
        await provider.search(
            request(),
            RequestContext(request_id="cancel"),
            ExecutionContext.with_timeout(1, cancel_event=event),
        )
    assert cancelled.value.code is ProviderErrorCode.CANCELLED
