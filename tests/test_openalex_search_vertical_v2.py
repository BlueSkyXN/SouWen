"""Deterministic P4-02 vertical integration through Module, Manager, and OpenAlex SPI."""

from __future__ import annotations

import pytest

from souwen.models import Author, PaperResult, SearchResponse
from souwen.modules.search.application import (
    OrderedSearchProviderSelector,
    SearchModuleService,
    SearchProviderSelection,
)
from souwen.platform.provider_manager import ProviderManager
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderRef,
    RequestContext,
    SearchRequest,
)
from souwen.providers.information_sources.openalex import (
    OPENALEX_PROVIDER_MANIFEST,
    OpenAlexSearchProvider,
)


class _Client:
    async def search(self, query, filters=None, sort=None, page=1, per_page=10):
        return SearchResponse(
            query=query,
            source="openalex",
            total_results=1,
            page=page,
            per_page=per_page,
            results=[
                PaperResult(
                    source="openalex",
                    source_url="https://openalex.org/W2741809807",
                    title="Fixture paper",
                    authors=[Author(name="Fixture Author")],
                    doi="10.1000/fixture",
                    year=2026,
                    raw={"type": "article", "is_oa": True},
                )
            ],
        )

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_openalex_vertical_runs_only_through_provider_manager_and_search_module() -> None:
    client = _Client()
    manager = ProviderManager(config_resolver=lambda _manifest: {"enabled": True})
    manager.register_factory(
        package_id="openalex",
        export="OpenAlexSearchProvider",
        factory=lambda configuration, _secrets: OpenAlexSearchProvider(
            client, enabled=configuration["enabled"]
        ),
        provider_type=OpenAlexSearchProvider,
    )
    registrations = manager.discover((OPENALEX_PROVIDER_MANIFEST,))
    selection = SearchProviderSelection(
        provider=ProviderRef(id="openalex", kind="search"),
        adapter_id="openalex-search",
        yaml_priority=1,
    )
    service = SearchModuleService(
        manager,
        OrderedSearchProviderSelector({"paper": (selection,)}),
    )
    context = RequestContext(request_id="openalex-vertical-v2")

    page = await service.search(
        SearchRequest(query="fixture", domains=("paper",)),
        context,
        ExecutionContext.with_timeout(5),
    )

    assert registrations[0].accepted is True
    assert page.context == context
    assert page.items[0].id == "doi:10.1000/fixture"
    assert page.meta.requested == ("openalex",)
    assert page.meta.succeeded == ("openalex",)
    await manager.close_all()
