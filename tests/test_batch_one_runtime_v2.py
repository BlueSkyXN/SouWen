"""Target-runtime integration for Provider v2 batch one."""

from __future__ import annotations

import asyncio

from souwen.config import SouWenConfig
from souwen.models import Author, FetchResult as LegacyFetchResult, PaperResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchRequest,
    ProviderRef,
    RequestContext,
    SearchRequest,
)
from souwen.server import v2_runtime as runtime_module
from tests.support.provider_v2_batch_one import batch_one_paper, google_patent, response


_SEARCH_CLIENT_GLOBALS = {
    "arxiv": "ArxivClient",
    "biorxiv": "BioRxivClient",
    "crossref": "CrossrefClient",
    "dblp": "DblpClient",
    "europepmc": "EuropePmcClient",
    "google_patents": "GooglePatentsScraper",
    "hal": "HalClient",
    "huggingface": "HuggingFaceClient",
    "iacr": "IacrClient",
    "osti": "OstiClient",
    "pmc": "PmcClient",
    "pubmed": "PubMedClient",
}
_EXPECTED_SEARCH_CALLS = {
    "arxiv": (("runtime",), {"max_results": 10}),
    "biorxiv": (("runtime",), {"per_page": 10}),
    "crossref": (("runtime",), {"rows": 10, "offset": 0}),
    "dblp": (("runtime",), {"hits": 10, "first": 0}),
    "europepmc": (("runtime",), {"page_size": 10}),
    "google_patents": (("runtime",), {"num_results": 10}),
    "hal": (("runtime",), {"rows": 10}),
    "huggingface": ((), {"query": "runtime", "top_n": 10}),
    "iacr": (("runtime",), {"max_results": 10}),
    "osti": (("runtime",), {"rows": 10, "page": 1}),
    "pmc": (("runtime",), {"retmax": 10, "retstart": 0}),
    "pubmed": (("runtime",), {"retmax": 10, "retstart": 0}),
}


class _OstiClient:
    async def search(self, query, rows=10, page=1):
        return SearchResponse(
            query=query,
            source="osti",
            total_results=1,
            page=page,
            per_page=rows,
            results=[
                PaperResult(
                    source="osti",
                    title="Runtime OSTI fixture",
                    authors=[Author(name="Runtime Researcher")],
                    source_url="https://www.osti.gov/biblio/3012392",
                    raw={"osti_id": "3012392", "product_type": "Report"},
                )
            ],
        )

    async def close(self):
        return None


class _ArxivFulltextClient:
    async def get_fulltext(self, paper_id):
        return LegacyFetchResult(
            url=f"https://arxiv.org/abs/{paper_id}",
            final_url=f"https://arxiv.org/html/{paper_id}",
            source="arxiv_fulltext",
            title="Runtime arXiv fixture",
            content="Runtime full text " * 8,
            content_format="text",
        )

    async def close(self):
        return None


def _context(value: str) -> RequestContext:
    return RequestContext(request_id=value)


def _fake_search_client(provider_id, calls, closed):
    result = response(
        provider_id,
        google_patent() if provider_id == "google_patents" else batch_one_paper(provider_id),
    )

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def search(self, *args, **kwargs):
            calls[provider_id] = (args, kwargs)
            return result

        async def close(self):
            closed.add(provider_id)

    return Client


def test_batch_one_catalog_and_explicit_search_fetch_are_wired(monkeypatch) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr(runtime_module, "OstiClient", _OstiClient)
    monkeypatch.setattr(runtime_module, "ArxivFulltextClient", _ArxivFulltextClient)
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            sources={
                "osti": {"enabled": True},
                "arxiv_fulltext": {"enabled": True},
            }
        )
    )

    catalog = {item.provider: item for item in runtime.services.provider_items}
    assert len(catalog) == 104
    assert catalog["osti"].availability == "available"
    assert catalog["arxiv_fulltext"].availability == "available"
    assert "opencitations" not in catalog
    assert {"osti-search", "arxiv_fulltext-fetch"}.issubset(runtime.manager.eligible_adapter_ids)

    search_page = asyncio.run(
        runtime.services.search.search(
            SearchRequest(
                query="energy",
                domains=("paper",),
                providers=(ProviderRef(id="osti", kind="search"),),
            ),
            _context("batch-one-search"),
            ExecutionContext.with_timeout(5),
        )
    )
    assert search_page.items[0].id == "osti:3012392"

    fetch_batch = asyncio.run(
        runtime.services.fetch.fetch(
            FetchRequest(
                targets=("https://arxiv.org/abs/2601.00001",),
                providers=(ProviderRef(id="arxiv_fulltext", kind="fetch"),),
            ),
            _context("batch-one-fetch"),
            ExecutionContext.with_timeout(5),
        )
    )
    assert fetch_batch.items[0].status == "success"
    assert fetch_batch.items[0].provenance[0].provider == "arxiv_fulltext"
    asyncio.run(runtime.close())


def test_pubmed_optional_key_is_resolved_without_becoming_required_or_public(monkeypatch) -> None:
    captured: list[str | None] = []

    class _PubMedClient:
        def __init__(self, api_key=None):
            captured.append(api_key)

        async def search(self, query, retmax=10, retstart=0):
            return SearchResponse(
                query=query,
                source="pubmed",
                total_results=0,
                page=1,
                per_page=retmax,
                results=[],
            )

        async def close(self):
            return None

    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr(runtime_module, "PubMedClient", _PubMedClient)
    secret = "runtime-only-optional-key"
    runtime = runtime_module.build_target_runtime(SouWenConfig(pubmed_api_key=secret))

    page = asyncio.run(
        runtime.services.search.search(
            SearchRequest(
                query="medicine",
                domains=("paper",),
                providers=(ProviderRef(id="pubmed", kind="search"),),
            ),
            _context("batch-one-pubmed"),
            ExecutionContext.with_timeout(5),
        )
    )

    assert page.items == ()
    assert captured == [secret]
    assert secret not in repr(runtime.services.provider_items)
    asyncio.run(runtime.close())


def test_every_batch_one_search_factory_constructs_dispatches_and_closes(monkeypatch) -> None:
    calls = {}
    closed = set()
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    for provider_id, global_name in _SEARCH_CLIENT_GLOBALS.items():
        monkeypatch.setattr(
            runtime_module,
            global_name,
            _fake_search_client(provider_id, calls, closed),
        )
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            sources={provider_id: {"enabled": True} for provider_id in _SEARCH_CLIENT_GLOBALS}
        )
    )

    for provider_id in _SEARCH_CLIENT_GLOBALS:
        domain = "patent" if provider_id == "google_patents" else "paper"
        page = asyncio.run(
            runtime.services.search.search(
                SearchRequest(
                    query="runtime",
                    domains=(domain,),
                    providers=(ProviderRef(id=provider_id, kind="search"),),
                ),
                _context(f"batch-one-{provider_id}"),
                ExecutionContext.with_timeout(5),
            )
        )
        assert page.items

    assert calls == _EXPECTED_SEARCH_CALLS
    asyncio.run(runtime.close())
    assert closed == set(_SEARCH_CLIENT_GLOBALS)
