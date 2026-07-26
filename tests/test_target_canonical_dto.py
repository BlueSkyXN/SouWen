"""Deterministic conformance tests for the Phase 4 canonical DTO binding."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from souwen.platform.provider_spi import (
    ContentMetadata,
    EvidenceItem,
    FetchBatch,
    FetchMeta,
    FetchRequest,
    FetchResult,
    LLMSearchRequest,
    LLMSearchResult,
    PageInfo,
    ProviderFailure,
    ProviderRef,
    Provenance,
    RequestContext,
    SearchItem,
    SearchFilters,
    SearchMeta,
    SearchPage,
    SearchRequest,
    Usage,
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


def test_python_binding_validates_the_language_neutral_golden_fixtures() -> None:
    fixture_path = Path(__file__).parent / "contracts" / "fixtures" / "target_api_contract_v2.json"
    goldens = json.loads(fixture_path.read_text(encoding="utf-8"))["goldens"]

    assert SearchPage.model_validate(goldens["search_partial_success"]).meta.partial is True
    assert LLMSearchResult.model_validate(goldens["llm_search_evidence"]).usage.cost is None
    assert (
        FetchBatch.model_validate(goldens["fetch_low_quality_partial"]).items[0].content == "short"
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


def test_search_and_llm_requests_reject_blank_and_duplicate_providers() -> None:
    provider = ProviderRef(id="fixture-llm", kind="llm_search")

    with pytest.raises(ValidationError):
        SearchRequest(query="   ", domains=("paper",))
    with pytest.raises(ValidationError):
        LLMSearchRequest(query="query", providers=(provider, provider), strategy="single")
    with pytest.raises(ValidationError):
        SearchFilters(year_from=2026, year_to=2025)


@pytest.mark.parametrize(
    "domain",
    ("social", "office", "developer", "cn_tech", "knowledge"),
)
def test_search_request_preserves_extended_registry_domains(domain: str) -> None:
    assert SearchRequest(query="fixture", domains=(domain,)).domains == (domain,)


def test_llm_result_requires_evidence_and_always_serializes_nullable_usage() -> None:
    result = LLMSearchResult(
        query="fixture query",
        items=(_search_item("fixture-item-001"),),
        evidence=(
            EvidenceItem(
                id="evidence-001",
                item_id="fixture-item-001",
                provider="fixture-llm",
                public_url="https://example.com/evidence",
                title_or_snippet="Fixture evidence",
                retrieved_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
            ),
        ),
        answer="Fixture factual answer [evidence-001]",
        meta=SearchMeta(),
        usage=Usage(),
        context=_context("fixture-request-002"),
    )

    assert result.model_dump(mode="json")["usage"] == {
        "input_tokens": None,
        "output_tokens": None,
        "cost": None,
        "currency": None,
    }
    assert result.evidence[0].item_id == result.items[0].id
    with pytest.raises(ValidationError):
        result.model_copy(update={"evidence": ()}).model_validate(
            result.model_copy(update={"evidence": ()}).model_dump()
        )
    with pytest.raises(ValidationError):
        LLMSearchResult(
            query="fixture query",
            items=result.items,
            evidence=result.evidence,
            answer="Uncited factual paragraph",
            meta=SearchMeta(),
            usage=Usage(),
            context=result.context,
        )


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
