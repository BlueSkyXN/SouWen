"""Nine-case matrix for the initial Provider v2 Search specifications."""

from __future__ import annotations

from datetime import date
import importlib

import pytest

from souwen.providers.runtime_clients.models import (
    Applicant,
    Author,
    BookResult,
    PaperResult,
    PatentResult,
    ResearchOutputResult,
    SearchResponse,
    WebSearchResult,
)
from souwen.platform.provider_spi import SearchPageRequest, SearchRequest
from souwen.platform.provider_spec import ClientSearchProvider, ClientSearchProviderSpec
from souwen.providers.catalog import builtin_provider_manifests
from souwen.providers.information_sources.arxiv import ArxivSearchProvider
from souwen.providers.information_sources.biorxiv import BioRxivSearchProvider
from souwen.providers.information_sources.crossref import CrossrefSearchProvider
from souwen.providers.information_sources.doaj import DoajSearchProvider
from souwen.providers.information_sources.eric import EricSearchProvider
from souwen.providers.information_sources.epo_ops import EpoOpsSearchProvider
from souwen.providers.information_sources.europepmc import EuropePmcSearchProvider
from souwen.providers.information_sources.google_patents import GooglePatentsSearchProvider
from souwen.providers.information_sources.hal import HalSearchProvider
from souwen.providers.information_sources.huggingface import HuggingFaceSearchProvider
from souwen.providers.information_sources.iacr import IacrSearchProvider
from souwen.providers.information_sources.openalex import OpenAlexSearchProvider
from souwen.providers.information_sources.openaire import OpenAireSearchProvider
from souwen.providers.information_sources.osti import OstiSearchProvider
from souwen.providers.information_sources.patentsview import PatentsViewSearchProvider
from souwen.providers.information_sources.pmc import PmcSearchProvider
from souwen.providers.information_sources.pubmed import PubMedSearchProvider
from souwen.providers.information_sources.semantic_scholar import SemanticScholarSearchProvider
from souwen.providers.information_sources.uspto_odp import UsptoOdpSearchProvider
from souwen.providers.information_sources.zenodo import ZenodoSearchProvider
from souwen.providers.information_sources.github import GitHubSearchProvider
from souwen.providers.information_sources.stackoverflow import StackOverflowSearchProvider
from souwen.providers.information_sources.wikipedia import WikipediaSearchProvider
from souwen.providers.information_sources.youtube import YouTubeSearchProvider
from souwen.providers.information_sources.datacite import DataCiteSearchProvider
from souwen.providers.information_sources.doab import DOABSearchProvider
from souwen.providers.information_sources.figshare import FigshareSearchProvider
from souwen.providers.information_sources.internet_archive import InternetArchiveSearchProvider
from souwen.providers.information_sources.library_of_congress import (
    LibraryOfCongressSearchProvider,
)
from souwen.providers.information_sources.open_library import OpenLibrarySearchProvider
from souwen.providers.information_sources.wikisource import WikisourceSearchProvider
from tests.support.provider_v2_batch_one import (
    batch_one_paper as _batch_one_paper,
    google_patent as _google_patent,
    response as _response,
)
from tests.support.provider_v2_batch_two import (
    batch_two_paper as _batch_two_paper,
    batch_two_patent as _batch_two_patent,
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


def _web_response(provider_id: str, *, empty: bool = False) -> SearchResponse:
    url = {
        "coolapk": "https://www.coolapk.com/feed/provider-v2",
        "hostloc": "https://hostloc.com/thread-provider-v2.html",
        "juejin": "https://juejin.cn/post/provider-v2",
        "nodeseek": "https://www.nodeseek.com/post-provider-v2-1",
        "v2ex": "https://www.v2ex.com/t/provider-v2",
        "xiaohongshu": "https://www.xiaohongshu.com/explore/provider-v2",
        "youtube": "https://www.youtube.com/watch?v=provider-v2",
    }.get(provider_id, f"https://example.test/{provider_id}")
    results = []
    if not empty:
        results.append(
            WebSearchResult(
                source=provider_id,
                title=f"{provider_id} conformance record",
                url=url,
                snippet="deterministic web fixture",
                engine=provider_id,
            )
        )
    return SearchResponse(
        query="conformance",
        source=provider_id,
        total_results=len(results),
        page=1,
        per_page=10,
        results=results,
    )


def _web_definition(provider_id: str, provider_type: type, domain: str):
    return SearchConformanceDefinition(
        provider_id=provider_id,
        build_provider=lambda client, enabled: provider_type(client, enabled=enabled),
        request=SearchRequest(
            query="conformance",
            domains=(domain,),
            page=SearchPageRequest(limit=5),
        ),
        success_response=_web_response(provider_id),
        empty_response=_web_response(provider_id, empty=True),
        invalid_response=object(),
    )


_BATCH_FIVE_SEARCH_IDS = (
    "baidu",
    "bing",
    "bing_cn",
    "brave",
    "coolapk",
    "csdn",
    "duckduckgo",
    "duckduckgo_images",
    "duckduckgo_news",
    "duckduckgo_videos",
    "google",
    "hostloc",
    "juejin",
    "mojeek",
    "nodeseek",
    "startpage",
    "v2ex",
    "xiaohongshu",
    "yahoo",
    "yandex",
)
_BATCH_SIX_SELF_HOSTED_IDS = ("searxng",)


def _migrated_legacy_web_definitions() -> tuple[SearchConformanceDefinition, ...]:
    definitions = []
    for provider_id in (*_BATCH_FIVE_SEARCH_IDS, *_BATCH_SIX_SELF_HOSTED_IDS):
        module = importlib.import_module(f"souwen.providers.information_sources.{provider_id}")
        spec = next(
            value for value in vars(module).values() if isinstance(value, ClientSearchProviderSpec)
        )
        provider_type = next(
            value
            for value in vars(module).values()
            if isinstance(value, type)
            and value is not ClientSearchProvider
            and issubclass(value, ClientSearchProvider)
            and value.__module__.startswith(module.__name__)
        )
        definitions.append(_web_definition(provider_id, provider_type, spec.domain))
    return tuple(definitions)


_BOOK_URLS = {
    "doab": "https://directory.doabooks.org/handle/20.500.12854/1",
    "internet_archive": "https://archive.org/details/provider-v2",
    "library_of_congress": "https://www.loc.gov/item/provider-v2/",
    "open_library": "https://openlibrary.org/works/OL1W",
    "wikisource": "https://zh.wikisource.org/wiki/Provider_v2",
}


def _book(provider_id: str) -> BookResult:
    return BookResult(
        source=provider_id,
        source_record_id="provider-v2",
        title=f"{provider_id} conformance record",
        languages=["zh" if provider_id == "wikisource" else "en"],
        source_url=_BOOK_URLS[provider_id],
    )


def _research_output(provider_id: str) -> ResearchOutputResult:
    return ResearchOutputResult(
        source=provider_id,
        source_record_id="10.1234/provider-v2" if provider_id == "datacite" else "1234",
        title=f"{provider_id} conformance record",
        source_url=(
            "https://doi.org/10.1234/provider-v2"
            if provider_id == "datacite"
            else "https://figshare.com/articles/dataset/provider-v2/1234"
        ),
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
    *(
        _definition(
            provider_id,
            provider_type,
            _response(provider_id, _batch_two_paper(provider_id)),
        )
        for provider_id, provider_type in (
            ("doaj", DoajSearchProvider),
            ("openaire", OpenAireSearchProvider),
            ("semantic_scholar", SemanticScholarSearchProvider),
            ("zenodo", ZenodoSearchProvider),
        )
    ),
    *(
        _definition(
            provider_id,
            provider_type,
            _response(provider_id, _batch_two_patent(provider_id)),
            domain="patent",
        )
        for provider_id, provider_type in (
            ("epo_ops", EpoOpsSearchProvider),
            ("uspto_odp", UsptoOdpSearchProvider),
        )
    ),
    *(
        _web_definition(provider_id, provider_type, domain)
        for provider_id, provider_type, domain in (
            ("github", GitHubSearchProvider, "developer"),
            ("stackoverflow", StackOverflowSearchProvider, "developer"),
            ("wikipedia", WikipediaSearchProvider, "knowledge"),
            ("youtube", YouTubeSearchProvider, "videos"),
        )
    ),
    *(
        _definition(
            provider_id,
            provider_type,
            _response(provider_id, _book(provider_id)),
            domain="book",
        )
        for provider_id, provider_type in (
            ("doab", DOABSearchProvider),
            ("internet_archive", InternetArchiveSearchProvider),
            ("library_of_congress", LibraryOfCongressSearchProvider),
            ("open_library", OpenLibrarySearchProvider),
            ("wikisource", WikisourceSearchProvider),
        )
    ),
    *(
        _definition(
            provider_id,
            provider_type,
            _response(provider_id, _research_output(provider_id)),
            domain="research_output",
        )
        for provider_id, provider_type in (
            ("datacite", DataCiteSearchProvider),
            ("figshare", FigshareSearchProvider),
        )
    ),
    *_migrated_legacy_web_definitions(),
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
    migrated_search_specs = {
        manifest.id
        for manifest in builtin_provider_manifests()
        if "search" in manifest.capabilities
    }

    assert {definition.provider_id for definition in DEFINITIONS} == migrated_search_specs
