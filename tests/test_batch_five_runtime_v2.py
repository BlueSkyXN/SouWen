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
from souwen.models import FetchResult as LegacyFetchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchRequest,
    ProviderRef,
    RequestContext,
    SearchRequest,
)
from souwen.server import v2_runtime as runtime_module


_RESULT_URLS = {
    "bilibili": "https://www.bilibili.com/video/BV1234567890",
    "coolapk": "https://www.coolapk.com/feed/1",
    "hostloc": "https://hostloc.com/thread-1-1-1.html",
    "juejin": "https://juejin.cn/post/1",
    "nodeseek": "https://www.nodeseek.com/post-1-1",
    "v2ex": "https://www.v2ex.com/t/1",
    "weibo": "https://m.weibo.cn/detail/1",
    "xiaohongshu": "https://www.xiaohongshu.com/explore/1",
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
    original_get = runtime_module.get_legacy_adapter
    clients = {
        provider_id: _fake_client(provider_id, constructor_calls, search_calls, closed)
        for provider_id in runtime_module._BATCH_FIVE_SEARCH_SOURCE_IDS
    }

    def fake_get(provider_id):
        if provider_id in clients:
            return SimpleNamespace(
                runtime_default_enabled=True,
                client_loader=lambda provider_id=provider_id: clients[provider_id],
            )
        return original_get(provider_id)

    monkeypatch.setattr(runtime_module, "get_legacy_adapter", fake_get)
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
            bilibili_sessdata="test-session",
            sources=sources,
        )
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}
    assert len(catalog) == 104
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
    expected_closed["duckduckgo"] += len(runtime_module._BATCH_FIVE_DDG_SITE_SOURCE_IDS)
    assert closed == expected_closed
    calls = {provider_id: values for provider_id, *values in constructor_calls}
    assert all(values[1] is False for values in calls.values())
    assert all(
        calls[provider_id][0].get("follow_redirects") is False
        for provider_id in clients
        if not provider_id.startswith("duckduckgo")
        and provider_id not in runtime_module._BATCH_FIVE_DDG_SITE_SOURCE_IDS
    )
    assert calls["duckduckgo"][0] == {}
    assert calls["baidu"][2] == "http://127.0.0.1:17890"
    assert all(values[3:] == [7, 1] for values in calls.values())
    assert calls["bilibili"][0] == {
        "follow_redirects": False,
        "sessdata": "test-session",
    }


def test_batch_five_public_target_fetch_factories_enter_dispatch_and_close(monkeypatch) -> None:
    events: list[tuple[str, str]] = []
    real_find_spec = runtime_module.importlib.util.find_spec
    monkeypatch.setattr(
        runtime_module.importlib.util,
        "find_spec",
        lambda name: object() if name in {"newspaper", "readability"} else real_find_spec(name),
    )

    def fake_client_type(provider_id: str):
        class Client:
            def __init__(self):
                events.append((provider_id, "construct"))

            async def __aenter__(self):
                events.append((provider_id, "enter"))
                return self

            async def __aexit__(self, *_args):
                events.append((provider_id, "exit"))

            async def fetch(self, url, timeout=30.0):
                events.append((provider_id, "fetch"))
                return LegacyFetchResult(
                    url=url,
                    final_url=url,
                    source=provider_id,
                    title="fixture",
                    content="useful runtime content",
                    content_format="text",
                )

        return Client

    monkeypatch.setattr(runtime_module, "NewspaperFetcherClient", fake_client_type("newspaper"))
    monkeypatch.setattr(runtime_module, "ReadabilityFetcherClient", fake_client_type("readability"))
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            sources={
                "newspaper": {"enabled": True},
                "readability": {"enabled": True},
            }
        )
    )

    async def exercise() -> None:
        for provider_id in ("newspaper", "readability"):
            batch = await runtime.services.fetch.fetch(
                FetchRequest(
                    targets=("https://1.1.1.1/page",),
                    providers=(ProviderRef(id=provider_id, kind="fetch"),),
                ),
                RequestContext(request_id=f"batch-five-{provider_id}"),
                ExecutionContext.with_timeout(5),
            )
            assert batch.items[0].status == "success"
            assert batch.items[0].provenance[0].provider == provider_id
        await runtime.close()

    asyncio.run(exercise())
    assert events == [
        ("newspaper", "construct"),
        ("newspaper", "enter"),
        ("newspaper", "fetch"),
        ("readability", "construct"),
        ("readability", "enter"),
        ("readability", "fetch"),
        ("newspaper", "exit"),
        ("readability", "exit"),
    ]


def test_real_batch_five_search_clients_construct_probe_and_close_without_network(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            bilibili_sessdata="test-session",
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


def test_public_target_fetch_catalog_is_not_eligible_without_optional_runtime(
    monkeypatch,
) -> None:
    real_find_spec = runtime_module.importlib.util.find_spec
    monkeypatch.setattr(
        runtime_module.importlib.util,
        "find_spec",
        lambda name: None if name in {"newspaper", "readability"} else real_find_spec(name),
    )
    runtime = runtime_module.build_target_runtime(SouWenConfig())
    catalog = {item.provider: item for item in runtime.services.provider_items}

    for provider_id in ("newspaper", "readability"):
        assert catalog[provider_id].availability == "unavailable"
        assert catalog[provider_id].reason == "not_eligible"
