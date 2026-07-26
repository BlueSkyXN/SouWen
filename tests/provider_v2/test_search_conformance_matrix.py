"""Nine-case matrix for the initial Provider v2 Search specifications."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from souwen.models import Applicant, Author, PaperResult, PatentResult
from souwen.platform.provider_spi import SearchRequest
from souwen.providers.information_sources.arxiv import ArxivSearchProvider
from souwen.providers.information_sources.biorxiv import BioRxivSearchProvider
from souwen.providers.information_sources.crossref import CrossrefSearchProvider
from souwen.providers.information_sources.dblp import DblpSearchProvider
from souwen.providers.information_sources.eric import EricSearchProvider
from souwen.providers.information_sources.europepmc import EuropePmcSearchProvider
from souwen.providers.information_sources.google_patents import GooglePatentsSearchProvider
from souwen.providers.information_sources.hal import HalSearchProvider
from souwen.providers.information_sources.huggingface import HuggingFaceSearchProvider
from souwen.providers.information_sources.iacr import IacrSearchProvider
from souwen.providers.information_sources.openalex import OpenAlexSearchProvider
from souwen.providers.information_sources.osti import OstiSearchProvider
from souwen.providers.information_sources.patentsview import PatentsViewSearchProvider
from souwen.providers.information_sources.pmc import PmcSearchProvider
from souwen.providers.information_sources.pubmed import PubMedSearchProvider
from tests.support.provider_v2_batch_one import (
    batch_one_paper as _batch_one_paper,
    google_patent as _google_patent,
    response as _response,
)
from tests.support.provider_v2_conformance import (
    SEARCH_CONFORMANCE_CASES,
    SearchConformanceDefinition,
    run_search_conformance_case,
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


def _definition(provider_id, provider_type, response, *, domain="paper"):
    return SearchConformanceDefinition(
        provider_id=provider_id,
        build_provider=lambda client, enabled: provider_type(client, enabled=enabled),
        request=SearchRequest(query="conformance", domains=(domain,)),
        success_response=response,
        empty_response=_response(provider_id),
        invalid_response=object(),
    )


DEFINITIONS = (
    _definition("arxiv", ArxivSearchProvider, _response("arxiv", _batch_one_paper("arxiv"))),
    _definition(
        "biorxiv",
        BioRxivSearchProvider,
        _response("biorxiv", _batch_one_paper("biorxiv")),
    ),
    _definition(
        "crossref",
        CrossrefSearchProvider,
        _response("crossref", _batch_one_paper("crossref")),
    ),
    _definition("dblp", DblpSearchProvider, _response("dblp", _batch_one_paper("dblp"))),
    _definition("eric", EricSearchProvider, _response("eric", _eric_paper())),
    _definition(
        "europepmc",
        EuropePmcSearchProvider,
        _response("europepmc", _batch_one_paper("europepmc")),
    ),
    _definition(
        "google_patents",
        GooglePatentsSearchProvider,
        _response("google_patents", _google_patent()),
        domain="patent",
    ),
    _definition("hal", HalSearchProvider, _response("hal", _batch_one_paper("hal"))),
    _definition(
        "huggingface",
        HuggingFaceSearchProvider,
        _response("huggingface", _batch_one_paper("huggingface")),
    ),
    _definition("iacr", IacrSearchProvider, _response("iacr", _batch_one_paper("iacr"))),
    _definition("openalex", OpenAlexSearchProvider, _response("openalex", _openalex_paper())),
    _definition("osti", OstiSearchProvider, _response("osti", _batch_one_paper("osti"))),
    _definition(
        "patentsview",
        PatentsViewSearchProvider,
        _response("patentsview", _patent()),
        domain="patent",
    ),
    _definition("pmc", PmcSearchProvider, _response("pmc", _batch_one_paper("pmc"))),
    _definition(
        "pubmed",
        PubMedSearchProvider,
        _response("pubmed", _batch_one_paper("pubmed")),
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
