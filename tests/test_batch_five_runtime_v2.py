"""Target-runtime integration for the retained Batch 5 scraper providers."""

from __future__ import annotations

import asyncio
from collections import Counter
from types import SimpleNamespace

from souwen.common_runtime.channel_overrides import (
    reviewed_source_max_retries,
    reviewed_source_proxy,
    reviewed_source_timeout_seconds,
    source_channel_overrides_enabled,
)
from souwen.config import SouWenConfig
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderRef,
    RequestContext,
    SearchRequest,
)
from souwen.server import v2_runtime as runtime_module


_RESULT_URLS = {
    "coolapk": "https://www.coolapk.com/feed/1",
    "juejin": "https://juejin.cn/post/1",
    "weibo": "https://m.weibo.cn/detail/1",
    "zhihu": "https://www.zhihu.com/question/1",
}


def _fake_client(provider_id, constructor_calls, search_calls, closed):
    class Client:
        def __init__(self, **kwargs):
            constructor_calls.append(
                (
                    provider_id,
                    kwargs,
                    source_channel_overrides_enabled(),
                    reviewed_source_proxy(),
                    reviewed_source_timeout_seconds(),
                    reviewed_source_max_retries(),
                )
            )

        async def search(self, query, max_results=20, **_kwargs):
            search_calls[provider_id] = (query, max_results)
            return SimpleNamespace(
                source=provider_id,
                page=1,
                total_results=1,
                results=[
                    SimpleNamespace(
                        source=provider_id,
                        title=f"{provider_id} result",
                        url=_RESULT_URLS.get(provider_id, "https://example.com/result"),
                        snippet="fixture",
                    )
                ],
            )

        async def close(self):
            if getattr(self, "_ddg_client", None) is not None:
                await self._ddg_client.close()
            closed[provider_id] += 1

    return Client


def test_every_batch_five_search_factory_dispatches_and_closes_with_reviewed_config(
    monkeypatch,
) -> None:
    constructor_calls, search_calls = [], {}
    closed: Counter[str] = Counter()
    clients = {
        provider_id: _fake_client(provider_id, constructor_calls, search_calls, closed)
        for provider_id in runtime_module._BATCH_FIVE_SEARCH_SOURCE_IDS
    }

    monkeypatch.setattr(runtime_module, "_BATCH_FIVE_CLIENT_TYPES", clients)
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    sources = {
        provider_id: {"enabled": True}
        for provider_id in runtime_module._BATCH_FIVE_SEARCH_SOURCE_IDS
    }
    sources["baidu"]["proxy"] = "http://127.0.0.1:17890"
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            timeout=7,
            max_retries=1,
            sources=sources,
        )
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}
    assert len(catalog) == 36
    assert all(catalog[provider_id].availability == "available" for provider_id in clients)

    async def exercise() -> None:
        for manifest, spec, *_rest in runtime_module._BATCH_FIVE_SEARCH_BINDINGS:
            page = await runtime.services.search.search(
                SearchRequest(
                    query="runtime",
                    domains=(spec.domain,),
                    providers=(ProviderRef(id=manifest.id, kind="search"),),
                ),
                RequestContext(request_id=f"batch-five-{manifest.id}"),
                ExecutionContext.with_timeout(5),
            )
            assert page.items[0].provenance[0].provider == manifest.id
        await runtime.close()

    asyncio.run(exercise())
    assert set(search_calls) == set(clients)
    expected_closed = Counter({provider_id: 1 for provider_id in clients})
    assert closed == expected_closed
    calls = {provider_id: values for provider_id, *values in constructor_calls}
    assert all(values[1] is False for values in calls.values())
    assert all(
        calls[provider_id][0].get("follow_redirects") is False
        for provider_id in clients
        if not provider_id.startswith("duckduckgo")
        and provider_id not in runtime_module._BATCH_FIVE_DDG_SITE_SOURCE_IDS
    )
    assert calls["baidu"][2] == "http://127.0.0.1:17890"
    assert all(values[3:] == [7, 1] for values in calls.values())


def test_real_batch_five_search_clients_construct_probe_and_close_without_network(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            sources={
                provider_id: {"enabled": True}
                for provider_id in runtime_module._BATCH_FIVE_SEARCH_SOURCE_IDS
            },
        )
    )

    async def exercise() -> None:
        for manifest, *_rest in runtime_module._BATCH_FIVE_SEARCH_BINDINGS:
            probe = await runtime.manager.probe(
                manifest.adapters[0].id,
                ExecutionContext.with_timeout(5),
            )
            assert probe.status == "available"
        await runtime.close()

    asyncio.run(exercise())
