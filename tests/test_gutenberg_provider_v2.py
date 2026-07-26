from __future__ import annotations

import pytest
from souwen.providers.runtime_clients.models import BookResult, SearchResponse
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.gutenberg import (
    GUTENBERG_PROVIDER_MANIFEST,
    GUTENBERG_PROVIDER_SPEC,
    GutenbergSearchProvider,
)


class _Client:
    def __init__(self, response: object):
        self.response, self.calls = response, []

    async def search(self, query: str, per_page: int = 10):
        self.calls.append((query, per_page))
        return self.response


@pytest.mark.asyncio
async def test_gutenberg_search_uses_local_catalog_without_page_or_egress() -> None:
    client = _Client(
        SearchResponse(
            query="alice",
            source="gutenberg",
            total_results=1,
            per_page=10,
            results=[
                BookResult(
                    source="gutenberg",
                    source_record_id="11",
                    title="Alice",
                    source_url="https://www.gutenberg.org/ebooks/11",
                )
            ],
        )
    )
    page = await GutenbergSearchProvider(client).search(
        SearchRequest(query="alice", domains=("book",)),
        RequestContext(request_id="gutenberg"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("alice", 10)]
    assert page.items[0].id == "gutenberg:11"
    assert GUTENBERG_PROVIDER_MANIFEST.network.egress_hosts == ()
    assert GUTENBERG_PROVIDER_MANIFEST.network.proxy_supported is False
    assert GUTENBERG_PROVIDER_SPEC.transport.operations == ("search",)


def test_gutenberg_local_store_rejects_network_execution_declarations() -> None:
    network = GUTENBERG_PROVIDER_MANIFEST.network.model_copy(update={"proxy_supported": True})
    manifest = GUTENBERG_PROVIDER_MANIFEST.model_copy(update={"network": network})

    with pytest.raises(ValueError, match="cannot declare network execution"):
        validate_spec_manifest(GUTENBERG_PROVIDER_SPEC, manifest)
