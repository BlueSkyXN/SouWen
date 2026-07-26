"""Nine-case matrix for the initial Provider v2 Search specifications."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from souwen.models import Applicant, Author, PaperResult, PatentResult, SearchResponse
from souwen.platform.provider_spi import SearchRequest
from souwen.providers.information_sources.eric import EricSearchProvider
from souwen.providers.information_sources.openalex import OpenAlexSearchProvider
from souwen.providers.information_sources.patentsview import PatentsViewSearchProvider
from tests.support.provider_v2_conformance import (
    SEARCH_CONFORMANCE_CASES,
    SearchConformanceDefinition,
    run_search_conformance_case,
)


def _response(source: str, *results: object) -> SearchResponse:
    return SearchResponse(
        query="conformance",
        source=source,
        total_results=len(results),
        page=1,
        per_page=10,
        results=list(results),
    )


def _openalex_paper() -> PaperResult:
    return PaperResult(
        source="openalex",
        title="OpenAlex conformance record",
        authors=[Author(name="Ada Researcher")],
        doi="10.1000/provider-v2",
        year=2026,
        source_url="https://openalex.org/W123456789",
        raw={"type": "article", "is_oa": True},
    )


def _eric_paper() -> PaperResult:
    return PaperResult(
        source="eric",
        title="ERIC conformance record",
        authors=[Author(name="Grace Educator")],
        year=2026,
        source_url="https://eric.ed.gov/?id=ED123456",
        raw={
            "eric_id": "ED123456",
            "publication_types": ["Journal Articles"],
            "language": ["en"],
            "fulltext_authorized": True,
        },
    )


def _patent() -> PatentResult:
    return PatentResult(
        source="patentsview",
        patent_id="12345678",
        title="PatentsView conformance record",
        applicants=[Applicant(name="Example Corp")],
        publication_date=date(2026, 1, 2),
        source_url="https://search.patentsview.org/patent/12345678",
        raw={"patent_type": "utility"},
    )


DEFINITIONS = (
    SearchConformanceDefinition(
        provider_id="openalex",
        build_provider=lambda client, enabled: OpenAlexSearchProvider(client, enabled=enabled),
        request=SearchRequest(query="conformance", domains=("paper",)),
        success_response=_response("openalex", _openalex_paper()),
        empty_response=_response("openalex"),
        invalid_response=object(),
    ),
    SearchConformanceDefinition(
        provider_id="eric",
        build_provider=lambda client, enabled: EricSearchProvider(client, enabled=enabled),
        request=SearchRequest(query="conformance", domains=("paper",)),
        success_response=_response("eric", _eric_paper()),
        empty_response=_response("eric"),
        invalid_response=object(),
    ),
    SearchConformanceDefinition(
        provider_id="patentsview",
        build_provider=lambda client, enabled: PatentsViewSearchProvider(client, enabled=enabled),
        request=SearchRequest(query="conformance", domains=("patent",)),
        success_response=_response("patentsview", _patent()),
        empty_response=_response("patentsview"),
        invalid_response=object(),
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", SEARCH_CONFORMANCE_CASES)
@pytest.mark.parametrize("definition", DEFINITIONS, ids=lambda item: item.provider_id)
async def test_search_provider_conformance_matrix(
    definition: SearchConformanceDefinition,
    case_id: str,
) -> None:
    await run_search_conformance_case(definition, case_id)


def test_each_search_provider_declares_exactly_the_nine_stable_cases() -> None:
    assert SEARCH_CONFORMANCE_CASES == (
        "success",
        "empty",
        "invalid_config",
        "cancellation",
        "rate_limit",
        "invalid_upstream",
        "policy_blocked",
        "probe_close",
        "redaction",
    )
    inventory_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "internal"
        / "provider-migrations"
        / "b0-inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    migrated_search_specs = {
        record["source_id"]
        for record in inventory["records"]
        if record["migration_status"] == "migrated"
        and record["target_capability"] == "search"
        and record["target_spec_identity"] is not None
    }

    assert {definition.provider_id for definition in DEFINITIONS} == migrated_search_specs
