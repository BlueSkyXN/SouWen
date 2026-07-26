"""Target-runtime integration for all 11 Batch 4 catalog providers."""

from __future__ import annotations

import asyncio
from collections import Counter

from souwen.common_runtime.channel_overrides import (
    reviewed_source_max_retries,
    reviewed_source_proxy,
    reviewed_source_timeout_seconds,
    source_channel_overrides_enabled,
)
from souwen.config import SouWenConfig
from souwen.models import BookResult, ResearchOutputResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderRef,
    RequestContext,
    SearchRequest,
)
from souwen.server import v2_runtime as runtime_module


_CLIENT_GLOBALS = {
    "datacite": "DataCiteClient",
    "doab": "DOABClient",
    "figshare": "FigshareClient",
    "gutenberg": "GutenbergLocalCatalogClient",
    "internet_archive": "InternetArchiveClient",
    "library_of_congress": "LibraryOfCongressClient",
    "librivox": "LibriVoxClient",
    "oapen": "OAPENClient",
    "open_library": "OpenLibraryClient",
    "taiwan_new_books": "TaiwanNewBooksLocalCatalogClient",
    "wikisource": "WikisourceClient",
}

_BOOK_URLS = {
    "doab": "https://directory.doabooks.org/handle/20.500.12854/1",
    "gutenberg": "https://www.gutenberg.org/ebooks/11",
    "internet_archive": "https://archive.org/details/runtime-book",
    "library_of_congress": "https://www.loc.gov/item/runtime-book/",
    "librivox": "https://librivox.org/audiobook/runtime-book",
    "oapen": "https://library.oapen.org/handle/20.500.12657/1",
    "open_library": "https://openlibrary.org/works/OL1W",
    "taiwan_new_books": "https://data.gov.tw/api/front/dataset/detail?nid=6730",
    "wikisource": "https://zh.wikisource.org/wiki/Runtime",
}


def _configured(tmp_path) -> SouWenConfig:
    sources = {provider_id: {"enabled": True} for provider_id in _CLIENT_GLOBALS}
    sources["datacite"]["proxy"] = "http://127.0.0.1:17890"
    return SouWenConfig(
        local_catalog_path=str(tmp_path / "catalog.sqlite3"),
        timeout=7,
        max_retries=1,
        sources=sources,
    )


def _result(provider_id: str):
    if provider_id in {"datacite", "figshare"}:
        return ResearchOutputResult(
            source=provider_id,
            source_record_id="10.1234/runtime" if provider_id == "datacite" else "1234",
            title=f"{provider_id} runtime fixture",
            source_url=(
                "https://doi.org/10.1234/runtime"
                if provider_id == "datacite"
                else "https://figshare.com/articles/dataset/runtime/1234"
            ),
        )
    return BookResult(
        source=provider_id,
        source_record_id=(
            "zh:1"
            if provider_id == "wikisource"
            else "9789861234567"
            if provider_id == "taiwan_new_books"
            else "runtime-book"
        ),
        title=f"{provider_id} runtime fixture",
        languages=["zh" if provider_id in {"wikisource", "taiwan_new_books"} else "en"],
        source_url=_BOOK_URLS[provider_id],
    )


def _fake_client(provider_id, constructor_calls, search_calls, closed):
    class Client:
        def __init__(self, *args, **kwargs):
            constructor_calls.append(
                (
                    provider_id,
                    args,
                    kwargs,
                    source_channel_overrides_enabled(),
                    reviewed_source_proxy(),
                    reviewed_source_timeout_seconds(),
                    reviewed_source_max_retries(),
                )
            )

        async def search(self, query, **kwargs):
            search_calls[provider_id] = (query, kwargs)
            limit = kwargs.get("per_page", kwargs.get("page_size", 10))
            return SearchResponse(
                query=query,
                source=provider_id,
                total_results=1,
                page=1,
                per_page=limit,
                results=[_result(provider_id)],
            )

        async def close(self):
            closed[provider_id] += 1

    return Client


def test_every_batch_four_factory_dispatches_and_closes_with_reviewed_config(
    monkeypatch, tmp_path
) -> None:
    constructor_calls, search_calls = [], {}
    closed: Counter[str] = Counter()
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr(runtime_module, "gutenberg_catalog_ready", lambda _path: True)
    monkeypatch.setattr(runtime_module, "taiwan_new_books_catalog_ready", lambda _path: True)
    for provider_id, global_name in _CLIENT_GLOBALS.items():
        monkeypatch.setattr(
            runtime_module,
            global_name,
            _fake_client(provider_id, constructor_calls, search_calls, closed),
        )

    config = _configured(tmp_path)
    runtime = runtime_module.build_target_runtime(config)
    catalog = {item.provider: item for item in runtime.services.provider_items}
    assert len(catalog) == 104
    assert all(catalog[provider_id].availability == "available" for provider_id in _CLIENT_GLOBALS)

    async def exercise() -> None:
        for manifest, spec, *_rest in runtime_module._BATCH_FOUR_SEARCH_BINDINGS:
            page = await runtime.services.search.search(
                SearchRequest(
                    query="runtime",
                    domains=(spec.domain,),
                    providers=(ProviderRef(id=manifest.id, kind="search"),),
                ),
                RequestContext(request_id=f"batch-four-{manifest.id}"),
                ExecutionContext.with_timeout(5),
            )
            assert page.items[0].provenance[0].provider == manifest.id
        await runtime.close()

    asyncio.run(exercise())
    assert set(search_calls) == set(_CLIENT_GLOBALS)
    assert closed == Counter({provider_id: 1 for provider_id in _CLIENT_GLOBALS})
    calls = {provider_id: call for provider_id, *call in constructor_calls}
    assert all(call[2] is False for call in calls.values())
    assert calls["datacite"][3] == "http://127.0.0.1:17890"
    assert calls["gutenberg"][3] is None
    assert all(call[4:] == [7, 1] for call in calls.values())
    assert calls["gutenberg"][0] == (config.local_catalog_db_path,)
    assert calls["taiwan_new_books"][0] == (config.local_catalog_db_path,)


def test_local_catalog_provider_is_not_eligible_until_its_import_is_ready(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr(runtime_module, "gutenberg_catalog_ready", lambda _path: False)
    config = SouWenConfig(
        local_catalog_path=str(tmp_path / "catalog.sqlite3"),
        sources={"gutenberg": {"enabled": True}},
    )

    runtime = runtime_module.build_target_runtime(config)
    item = next(item for item in runtime.services.provider_items if item.provider == "gutenberg")

    assert item.availability == "unavailable"
    assert item.reason == "not_eligible"
    assert item.missing_fields == ()


def test_batch_four_default_search_uses_only_registry_default_providers(
    monkeypatch, tmp_path
) -> None:
    constructor_calls, search_calls = [], {}
    closed: Counter[str] = Counter()
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    monkeypatch.setattr(runtime_module, "gutenberg_catalog_ready", lambda _path: True)
    monkeypatch.setattr(runtime_module, "taiwan_new_books_catalog_ready", lambda _path: True)
    monkeypatch.setattr(
        runtime_module,
        "DataCiteClient",
        _fake_client("datacite", constructor_calls, search_calls, closed),
    )
    monkeypatch.setattr(
        runtime_module,
        "OpenLibraryClient",
        _fake_client("open_library", constructor_calls, search_calls, closed),
    )
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(local_catalog_path=str(tmp_path / "catalog.sqlite3"))
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}

    assert catalog["datacite"].availability == "available"
    assert catalog["open_library"].availability == "available"
    assert all(catalog[provider_id].availability == "available" for provider_id in _CLIENT_GLOBALS)

    async def exercise() -> None:
        for domain, provider_id in (
            ("book", "open_library"),
            ("research_output", "datacite"),
        ):
            page = await runtime.services.search.search(
                SearchRequest(query="runtime", domains=(domain,)),
                RequestContext(request_id=f"batch-four-default-{domain}"),
                ExecutionContext.with_timeout(5),
            )
            assert page.meta.requested == (provider_id,)
            assert page.items[0].provenance[0].provider == provider_id
        await runtime.close()

    asyncio.run(exercise())
    assert set(search_calls) == {"datacite", "open_library"}
