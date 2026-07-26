from __future__ import annotations

import pytest

from souwen.models import SearchResponse
from souwen.paper.core import CoreClient
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.core import (
    CORE_PROVIDER_MANIFEST,
    CORE_PROVIDER_SPEC,
    CoreSearchProvider,
)


class _Client:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response

    async def search(self, *_args, **_kwargs) -> SearchResponse:
        return self.response


def test_core_provider_v2_declares_required_bearer_secret() -> None:
    assert CORE_PROVIDER_SPEC.auth.reference == "CORE_API_KEY"
    assert CORE_PROVIDER_SPEC.auth.required is True
    assert CORE_PROVIDER_MANIFEST.secrets.references == ("CORE_API_KEY",)


@pytest.mark.asyncio
async def test_core_work_without_doi_or_fulltext_uses_stable_core_identity() -> None:
    paper = CoreClient._parse_work(
        {
            "id": "CORE-B2",
            "title": "CORE work",
            "authors": [{"name": "Core Author"}],
            "sourceFulltextUrls": [],
        }
    )
    assert paper.source_url == "https://core.ac.uk/works/CORE-B2"
    assert paper.raw["core_id"] == "CORE-B2"

    page = await CoreSearchProvider(
        _Client(
            SearchResponse(
                query="core",
                source="core",
                total_results=1,
                page=1,
                per_page=10,
                results=[paper],
            )
        )
    ).search(
        SearchRequest(query="core", domains=("paper",)),
        RequestContext(request_id="core-fallback"),
        ExecutionContext.with_timeout(5),
    )

    assert page.items[0].id == "core:CORE-B2"
    assert str(page.items[0].url) == "https://core.ac.uk/works/CORE-B2"
