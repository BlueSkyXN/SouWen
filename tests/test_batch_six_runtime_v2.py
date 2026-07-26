"""Target-runtime integration for the retained Batch 6 self-hosted providers."""

from __future__ import annotations

import asyncio
from collections import Counter
from types import SimpleNamespace

import pytest

from souwen.common_runtime.channel_overrides import (
    reviewed_source_max_retries,
    reviewed_source_proxy,
    reviewed_source_timeout_seconds,
    source_channel_overrides_enabled,
)
from souwen.config import SouWenConfig
from souwen.providers.runtime_clients.models import WebSearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderRef,
    RequestContext,
    SearchRequest,
)
from souwen.server import v2_runtime as runtime_module


def _fake_client(provider_id, constructor_calls, search_calls, closed):
    class Client:
        def __init__(self, *, instance_url, follow_redirects):
            constructor_calls.append(
                (
                    provider_id,
                    instance_url,
                    follow_redirects,
                    source_channel_overrides_enabled(),
                    reviewed_source_proxy(),
                    reviewed_source_timeout_seconds(),
                    reviewed_source_max_retries(),
                )
            )

        async def search(self, query, max_results=20):
            search_calls[provider_id] = (query, max_results)
            return WebSearchResponse(
                query=query,
                source=provider_id,
                total_results=1,
                results=[
                    WebSearchResult(
                        source=provider_id,
                        title=f"{provider_id} fixture",
                        url=f"https://example.test/{provider_id}",
                        snippet="fixture",
                        engine=provider_id,
                    )
                ],
            )

        async def close(self):
            closed[provider_id] += 1

    return Client


def test_batch_six_factories_use_only_preflighted_endpoints_and_close_once(monkeypatch) -> None:
    constructor_calls, search_calls = [], {}
    closed: Counter[str] = Counter()
    clients = {
        provider_id: _fake_client(provider_id, constructor_calls, search_calls, closed)
        for provider_id in runtime_module._BATCH_SIX_SELF_HOSTED_SOURCE_IDS
    }

    monkeypatch.setattr(runtime_module, "_SELF_HOSTED_CLIENT_TYPES", clients)
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            timeout=9,
            max_retries=1,
            whoogle_url="https://whoogle.example",
            sources={
                "searxng": {
                    "base_url": "http://127.0.0.1:8888/",
                    "proxy": "http://127.0.0.1:17890",
                    "timeout": 7,
                },
                "websurfx": {"base_url": "https://websurfx.internal:8080"},
            },
        )
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}
    assert len(catalog) == 104
    assert all(catalog[provider_id].availability == "available" for provider_id in clients)
    assert {f"{provider_id}-search" for provider_id in clients}.issubset(
        runtime.manager.eligible_adapter_ids
    )

    selector = runtime.services.search._selector
    default = selector.select_default(SearchRequest(query="default", domains=("web",)))
    assert default[0].provider.id not in clients

    async def exercise() -> None:
        for provider_id in clients:
            page = await runtime.services.search.search(
                SearchRequest(
                    query="runtime",
                    domains=("web",),
                    providers=(ProviderRef(id=provider_id, kind="search"),),
                ),
                RequestContext(request_id=f"batch-six-{provider_id}"),
                ExecutionContext.with_timeout(5),
            )
            assert page.items[0].provenance[0].provider == provider_id
        await runtime.close()
        await runtime.close()

    asyncio.run(exercise())
    assert set(search_calls) == set(clients)
    assert closed == Counter({provider_id: 1 for provider_id in clients})
    calls = {provider_id: values for provider_id, *values in constructor_calls}
    assert calls["searxng"][0] == "http://127.0.0.1:8888"
    assert calls["websurfx"][0] == "https://websurfx.internal:8080"
    assert calls["whoogle"][0] == "https://whoogle.example"
    assert all(values[1] is False for values in calls.values())
    assert all(values[2] is False for values in calls.values())
    assert calls["searxng"][3] == "http://127.0.0.1:17890"
    assert calls["searxng"][4:] == [7, 1]
    assert all(calls[provider_id][4:] == [9, 1] for provider_id in {"websurfx", "whoogle"})


def test_batch_six_catalog_distinguishes_missing_invalid_and_disabled_configuration(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            sources={
                "searxng": {"base_url": "ftp://invalid.example"},
                "whoogle": {"enabled": False},
            }
        )
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}

    assert catalog["searxng"].reason == "missing_configuration"
    assert catalog["searxng"].missing_fields == ("searxng_url",)
    assert catalog["websurfx"].reason == "missing_configuration"
    assert catalog["websurfx"].missing_fields == ("websurfx_url",)
    assert catalog["whoogle"].reason == "disabled"
    assert catalog["whoogle"].missing_fields == ()
    assert not {
        "searxng-search",
        "websurfx-search",
        "whoogle-search",
    }.intersection(runtime.manager.eligible_adapter_ids)
    asyncio.run(runtime.close())


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    (
        ("souwen.providers.runtime_clients.web.searxng", "SearXNGClient"),
        ("souwen.providers.runtime_clients.web.websurfx", "WebsurfxClient"),
        ("souwen.providers.runtime_clients.web.whoogle", "WhoogleClient"),
    ),
)
def test_explicit_self_hosted_client_endpoint_does_not_read_ambient_config(
    monkeypatch, module_name: str, class_name: str
) -> None:
    module = __import__(module_name, fromlist=[class_name])
    core_config = SimpleNamespace(
        timeout=30,
        max_retries=3,
        resolve_base_url=lambda *_args, **_kwargs: "http://ambient.internal:9999",
        resolve_proxy=lambda _source: None,
        resolve_headers=lambda _source: {},
        get_proxy=lambda: None,
    )
    monkeypatch.setattr(
        module,
        "get_config",
        lambda: pytest.fail("explicit Provider v2 endpoint must not read ambient config"),
    )
    monkeypatch.setattr(
        "souwen.common_runtime.provider_support.http_client.get_config", lambda: core_config
    )
    client = getattr(module, class_name)(
        instance_url="http://127.0.0.1:8080",
        follow_redirects=False,
    )
    assert client.instance_url == "http://127.0.0.1:8080"
    assert client.base_url == "http://127.0.0.1:8080"
    assert client._client.follow_redirects is False
    asyncio.run(client.close())
