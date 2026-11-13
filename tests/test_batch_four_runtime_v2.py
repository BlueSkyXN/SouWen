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
from souwen.config import DEFAULT_SEARCH_PROVIDERS, SouWenConfig
from souwen.providers.runtime_clients.models import BookResult, ResearchOutputResult, SearchResponse
from souwen.platform.provider_spi import (
    ExecutionContext,
    RequestContext,
    SearchRequest,
)
from souwen.server import v2_runtime as runtime_module


_CLIENT_GLOBALS = {
    "datacite": "DataCiteClient",
    "doab": "DOABClient",
    "figshare": "FigshareClient",
    "internet_archive": "InternetArchiveClient",
    "library_of_congress": "LibraryOfCongressClient",
    "open_library": "OpenLibraryClient",
    "wikisource": "WikisourceClient",
}

_BOOK_URLS = {
    "doab": "https://directory.doabooks.org/handle/20.500.12854/1",
    "internet_archive": "https://archive.org/details/runtime-book",
    "library_of_congress": "https://www.loc.gov/item/runtime-book/",
    "open_library": "https://openlibrary.org/works/OL1W",
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
        source_record_id="zh:1" if provider_id == "wikisource" else "runtime-book",
        title=f"{provider_id} runtime fixture",
        languages=["zh" if provider_id == "wikisource" else "en"],
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


def test_batch_four_default_search_uses_only_registry_default_providers(
    monkeypatch, tmp_path
) -> None:
    constructor_calls, search_calls = [], {}
    closed: Counter[str] = Counter()
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
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
    defaults = {domain: list(ids) for domain, ids in DEFAULT_SEARCH_PROVIDERS.items()}
    # 默认选源现在返回整个候选列表；把两个被 fake 的源设为各自领域的唯一默认，
    # 保持"默认路径只经注册的默认源"这一断言的确定性（其余 book/paper 候选未打桩）。
    defaults["book"] = ["open_library"]
    defaults["paper"] = ["datacite"]
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            local_catalog_path=str(tmp_path / "catalog.sqlite3"),
            search_defaults=defaults,
        )
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}

    assert catalog["datacite"].availability == "available"
    assert catalog["open_library"].availability == "available"
    assert all(catalog[provider_id].availability == "available" for provider_id in _CLIENT_GLOBALS)

    async def exercise() -> None:
        # open_library 与 datacite 均走默认选源路径（search_defaults 已收窄到单源）。
        for domain, provider_id in (
            ("book", "open_library"),
            ("paper", "datacite"),
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
