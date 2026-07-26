"""Target-runtime integration for the 13 retained Batch 2 Search providers."""

from __future__ import annotations

import asyncio

from souwen.config import SouWenConfig
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderRef,
    RequestContext,
    SearchRequest,
)
from souwen.server import v2_runtime as runtime_module
from tests.support.provider_v2_batch_one import response
from tests.support.provider_v2_batch_two import batch_two_paper, batch_two_patent


_CLIENT_GLOBALS = {
    "cnipa": "CnipaClient",
    "core": "CoreClient",
    "doaj": "DoajClient",
    "epo_ops": "EpoOpsClient",
    "ieee_xplore": "IeeeXploreClient",
    "openaire": "OpenAireClient",
    "patsnap": "PatSnapClient",
    "pqai": "PqaiClient",
    "semantic_scholar": "SemanticScholarClient",
    "the_lens": "TheLensClient",
    "uspto_odp": "UsptoOdpClient",
    "zenodo": "ZenodoClient",
    "zotero": "ZoteroClient",
}
_PATENT_PROVIDERS = {
    "cnipa",
    "epo_ops",
    "patsnap",
    "pqai",
    "the_lens",
    "uspto_odp",
}
_EXPECTED_CALLS = {
    "cnipa": (("runtime",), {"per_page": 10, "offset": 0}),
    "core": (("runtime",), {"limit": 10, "offset": 0}),
    "doaj": (("runtime",), {"page_size": 10, "page": 1}),
    "epo_ops": (("runtime",), {"range_begin": 1, "range_end": 10}),
    "ieee_xplore": (("runtime",), {"max_results": 10, "start_record": 1}),
    "openaire": (("runtime",), {"size": 10}),
    "patsnap": (("runtime",), {"limit": 10, "offset": 0}),
    "pqai": (("runtime",), {"n_results": 10}),
    "semantic_scholar": (("runtime",), {"fields": None, "limit": 10, "offset": 0}),
    "the_lens": (("runtime",), {"size": 10, "offset": 0}),
    "uspto_odp": (("runtime",), {"per_page": 10, "offset": 0}),
    "zenodo": (("runtime",), {"size": 10}),
    "zotero": (
        ("runtime",),
        {"qmode": "everything", "tag": None, "limit": 10, "start": 0},
    ),
}


def _fake_client(provider_id, constructor_calls, search_calls, closed):
    item = (
        batch_two_patent(provider_id)
        if provider_id in _PATENT_PROVIDERS
        else batch_two_paper(provider_id)
    )
    result = response(provider_id, item)

    class Client:
        def __init__(self, *args, **kwargs):
            constructor_calls[provider_id] = (args, kwargs)

        async def search(self, *args, **kwargs):
            search_calls[provider_id] = (args, kwargs)
            return result

        async def search_patents(self, *args, **kwargs):
            return await self.search(*args, **kwargs)

        async def search_applications(self, *args, **kwargs):
            return await self.search(*args, **kwargs)

        async def close(self):
            closed.add(provider_id)

    return Client


def _config() -> SouWenConfig:
    return SouWenConfig(
        sources={provider_id: {"enabled": True} for provider_id in _CLIENT_GLOBALS},
        cnipa_client_id="fixture-cnipa-id",
        cnipa_client_secret="fixture-cnipa-secret",
        core_api_key="fixture-core-key",
        epo_consumer_key="fixture-epo-key",
        epo_consumer_secret="fixture-epo-secret",
        ieee_api_key="fixture-ieee-key",
        patsnap_api_key="fixture-patsnap-key",
        pqai_api_token="fixture-pqai-token",
        lens_api_token="fixture-lens-token",
        uspto_api_key="fixture-uspto-key",
        zotero_api_key="fixture-zotero-key",
        zotero_library_id="12345",
        zotero_library_type="user",
    )


def test_every_batch_two_factory_constructs_dispatches_and_closes(monkeypatch) -> None:
    constructor_calls, search_calls, closed = {}, {}, set()
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    for provider_id, global_name in _CLIENT_GLOBALS.items():
        monkeypatch.setattr(
            runtime_module,
            global_name,
            _fake_client(provider_id, constructor_calls, search_calls, closed),
        )

    runtime = runtime_module.build_target_runtime(_config())
    catalog = {item.provider: item for item in runtime.services.provider_items}
    assert len(catalog) == 76
    assert all(catalog[provider_id].availability == "available" for provider_id in _CLIENT_GLOBALS)

    for provider_id in _CLIENT_GLOBALS:
        domain = "patent" if provider_id in _PATENT_PROVIDERS else "paper"
        page = asyncio.run(
            runtime.services.search.search(
                SearchRequest(
                    query="runtime",
                    domains=(domain,),
                    providers=(ProviderRef(id=provider_id, kind="search"),),
                ),
                RequestContext(request_id=f"batch-two-{provider_id}"),
                ExecutionContext.with_timeout(5),
            )
        )
        assert page.items

    assert set(constructor_calls) == set(_CLIENT_GLOBALS)
    assert search_calls == _EXPECTED_CALLS
    asyncio.run(runtime.close())
    assert closed == set(_CLIENT_GLOBALS)


def test_required_batch_two_configuration_is_reported_without_secret_values(monkeypatch) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(sources={"cnipa": {"enabled": True}, "zotero": {"enabled": True}})
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}

    assert catalog["cnipa"].reason == "missing_configuration"
    assert set(catalog["cnipa"].missing_fields) == {
        "cnipa_client_id",
        "cnipa_client_secret",
    }
    assert catalog["zotero"].reason == "missing_configuration"
    assert set(catalog["zotero"].missing_fields) == {
        "zotero_api_key",
        "zotero_library_id",
    }
    assert "fixture" not in repr(runtime.services.provider_items)
    asyncio.run(runtime.close())


def test_every_real_batch_two_client_factory_constructs_and_closes_without_network(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(_config())

    async def probe_and_close() -> None:
        for (
            manifest,
            _spec,
            _provider_type,
            _client_factory,
        ) in runtime_module._BATCH_TWO_SEARCH_BINDINGS:
            probe = await runtime.manager.probe(
                manifest.adapters[0].id,
                ExecutionContext.with_timeout(5),
            )
            assert probe.status == "available"
        await runtime.close()

    asyncio.run(probe_and_close())
