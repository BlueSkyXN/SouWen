"""Deterministic conformance tests for the Phase 4 canonical DTO binding."""

from __future__ import annotations


import pytest
from pydantic import ValidationError

from souwen.platform.provider_spi import (
    ContentMetadata,
    FetchBatch,
    FetchMeta,
    FetchRequest,
    FetchResult,
    PageInfo,
    ProviderFailure,
    ProviderRef,
    Provenance,
    RequestContext,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)


def _context(request_id: str = "fixture-request") -> RequestContext:
    return RequestContext(request_id=request_id)


def _provenance(provider: str = "fixture-provider") -> Provenance:
    return Provenance(provider=provider, outcome="success")


def _search_item(item_id: str = "fixture-item") -> SearchItem:
    return SearchItem(
        id=item_id,
        title="Fixture result",
        rank=1,
        provenance=(_provenance(),),
    )


def test_common_dtos_are_strict_frozen_and_use_api_major_two() -> None:
    context = _context()
    provider = ProviderRef(id="fixture-provider", kind="search")

    assert context.api_major == 2
    assert provider.model_config["extra"] == "forbid"
    assert provider.model_config["frozen"] is True
    assert provider.model_config["hide_input_in_errors"] is True

    with pytest.raises(ValidationError):
        RequestContext(request_id="fixture", unexpected="value")
    with pytest.raises(ValidationError):
        RequestContext(request_id="fixture", api_major=1)
    with pytest.raises(ValidationError):
        provider.id = "changed"  # type: ignore[misc]


def test_search_dto_preserves_partial_provider_outcome() -> None:
    page = SearchPage(
        items=(_search_item("doi:10.1000/fixture"),),
        page=PageInfo(limit=10),
        meta=SearchMeta(
            partial=True,
            requested=("openalex", "other"),
            succeeded=("openalex",),
            failed=(ProviderFailure(provider="other", code="provider_timeout"),),
        ),
        context=_context("fixture-request-001"),
    )

    assert page.model_dump(mode="json")["meta"] == {
        "partial": True,
        "requested": ["openalex", "other"],
        "succeeded": ["openalex"],
        "failed": [{"provider": "other", "code": "provider_timeout"}],
    }


@pytest.mark.parametrize(
    "domain",
    ("social", "developer", "cn_tech", "knowledge"),
)
def test_search_request_preserves_extended_registry_domains(domain: str) -> None:
    assert SearchRequest(query="fixture", domains=(domain,)).domains == (domain,)


def test_fetch_dto_enforces_target_cardinality_and_low_quality_partial_item() -> None:
    request = FetchRequest(targets=("https://example.com/short",))
    batch = FetchBatch(
        items=(
            FetchResult(
                target="https://example.com/short",
                status="success",
                content="short",
                content_metadata=ContentMetadata(
                    media_type="text/plain", quality="low", truncated=False
                ),
                provenance=(_provenance("builtin"),),
            ),
        ),
        meta=FetchMeta(partial=True),
        context=_context("fixture-request-003"),
    )

    assert str(request.targets[0]) == "https://example.com/short"
    assert batch.model_dump(mode="json")["meta"] == {"partial": True}
    with pytest.raises(ValidationError):
        FetchRequest(targets=())
    with pytest.raises(ValidationError):
        FetchRequest(targets=tuple(f"https://example.com/{index}" for index in range(21)))
    with pytest.raises(ValidationError):
        FetchResult(
            target="https://example.com/empty",
            status="success",
            content="",
            content_metadata=ContentMetadata(
                media_type="text/plain", quality="low", truncated=False
            ),
            provenance=(_provenance("builtin"),),
        )
