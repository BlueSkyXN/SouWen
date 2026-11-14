"""Target-runtime integration for the 13 retained Batch 2 Search providers."""

from __future__ import annotations

import asyncio
from importlib import import_module

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
    "doaj": "DoajClient",
    "epo_ops": "EpoOpsClient",
    "openaire": "OpenAireClient",
    "uspto_odp": "UsptoOdpClient",
    "zenodo": "ZenodoClient",
}
_PATENT_PROVIDERS = {
    "epo_ops",
    "uspto_odp",
}
_FETCH_NAMESPACE = frozenset()
_EXPECTED_CALLS = {
    "doaj": (("runtime",), {"page_size": 10, "page": 1}),
    "epo_ops": (("runtime",), {"range_begin": 1, "range_end": 10}),
    "openaire": (("runtime",), {"size": 10}),
    "uspto_odp": (("runtime",), {"per_page": 10, "offset": 0}),
    "zenodo": (("runtime",), {"size": 10}),
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
        epo_consumer_key="fixture-epo-key",
        epo_consumer_secret="fixture-epo-secret",
        uspto_api_key="fixture-uspto-key",
    )


def test_every_batch_two_factory_constructs_dispatches_and_closes(monkeypatch) -> None:
    constructor_calls, search_calls, closed = {}, {}, set()
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    for provider_id, global_name in _CLIENT_GLOBALS.items():
        _source_ns = (
            "souwen.providers.fetch_sources."
            if provider_id in _FETCH_NAMESPACE
            else "souwen.providers.information_sources."
        )
        monkeypatch.setattr(
            import_module(f"{_source_ns}{provider_id}.register"),
            global_name,
            _fake_client(provider_id, constructor_calls, search_calls, closed),
        )

    runtime = runtime_module.build_target_runtime(_config())
    catalog = {item.provider: item for item in runtime.services.provider_items}
    assert len(catalog) == 36
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
        SouWenConfig(sources={"epo_ops": {"enabled": True}, "youtube": {"enabled": True}})
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}

    assert catalog["epo_ops"].reason == "missing_configuration"
    assert set(catalog["epo_ops"].missing_fields) == {
        "epo_consumer_key",
        "epo_consumer_secret",
    }
    assert catalog["youtube"].reason == "missing_configuration"
    assert set(catalog["youtube"].missing_fields) == {
        "youtube_api_key",
    }
    assert "fixture" not in repr(runtime.services.provider_items)
    asyncio.run(runtime.close())


def test_every_real_batch_two_client_factory_constructs_and_closes_without_network(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(_config())

    async def probe_and_close() -> None:
        from souwen.server.v2_runtime import _discover_register_modules

        for module in _discover_register_modules():
            if module.MANIFEST.id in _CLIENT_GLOBALS:
                probe = await runtime.manager.probe(
                    module.MANIFEST.adapters[0].id,
                    ExecutionContext.with_timeout(5),
                )
                assert probe.status == "available"
        await runtime.close()

    asyncio.run(probe_and_close())
