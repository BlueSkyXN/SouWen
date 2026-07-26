"""Target-runtime integration for all 33 retained Batch 3 providers."""

from __future__ import annotations

import asyncio
from collections import Counter
from importlib import import_module

from souwen.core import http_client as http_client_module
from souwen.common_runtime.channel_overrides import (
    reviewed_source_proxy,
    source_channel_overrides_enabled,
    without_source_channel_overrides,
)
from souwen.core.scraper import base as scraper_base_module
from souwen.config import SouWenConfig
from souwen.models import FetchResult as LegacyFetchResult
from souwen.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchRequest,
    ProviderRef,
    RequestContext,
    SearchRequest,
)
from souwen.server import v2_runtime as runtime_module
from souwen.web import github as github_module
from souwen.web import kimi_code as kimi_code_module
from souwen.web import reddit as reddit_module
from souwen.web import stackoverflow as stackoverflow_module


_CLIENT_GLOBALS = {
    "aliyun_iqs": "AliyunIQSClient",
    "apify": "ApifyClient",
    "brave_api": "BraveApiClient",
    "cloudflare": "CloudflareBrowserClient",
    "deepwiki": "DeepWikiClient",
    "diffbot": "DiffbotClient",
    "exa": "ExaClient",
    "facebook": "FacebookClient",
    "feishu_drive": "FeishuDriveClient",
    "firecrawl": "FirecrawlClient",
    "github": "GitHubClient",
    "jina_reader": "JinaReaderClient",
    "kimi_code": "KimiCodeClient",
    "linkup": "LinkupClient",
    "linuxdo": "LinuxDoClient",
    "metaso": "MetasoClient",
    "perplexity": "PerplexityClient",
    "reddit": "RedditClient",
    "scraperapi": "ScraperAPIClient",
    "scrapingbee": "ScrapingBeeClient",
    "scrapingdog": "ScrapingDogClient",
    "scrapfly": "ScrapflyClient",
    "serpapi": "SerpApiClient",
    "serper": "SerperClient",
    "stackoverflow": "StackOverflowClient",
    "tavily": "TavilyClient",
    "twitter": "TwitterClient",
    "wayback": "WaybackClient",
    "wikipedia": "WikipediaClient",
    "xcrawl": "XCrawlClient",
    "youtube": "YouTubeClient",
    "zenrows": "ZenRowsClient",
    "zhipuai": "ZhipuAISearchClient",
}


def _batch_three_manifests():
    manifests = {
        manifest.id: manifest
        for manifest in (
            *(binding[0] for binding in runtime_module._BATCH_THREE_SEARCH_ONLY_BINDINGS),
            *(binding[0] for binding in runtime_module._BATCH_THREE_MULTI_BINDINGS),
            *(binding[0] for binding in runtime_module._BATCH_THREE_FETCH_ONLY_BINDINGS),
        )
    }
    return tuple(manifests[provider_id] for provider_id in sorted(manifests))


def _configured(
    *,
    include_optional: bool = True,
    source_overrides: dict[str, dict[str, object]] | None = None,
) -> SouWenConfig:
    values = {
        reference.lower(): f"fixture-{reference.lower()}"
        for manifest in _batch_three_manifests()
        for reference in (
            manifest.secrets.all_references if include_optional else manifest.secrets.references
        )
    }
    sources: dict[str, dict[str, object]] = {
        provider_id: {"enabled": True} for provider_id in _CLIENT_GLOBALS
    }
    for provider_id, overrides in (source_overrides or {}).items():
        sources[provider_id].update(overrides)
    return SouWenConfig(sources=sources, **values)


def _fake_client(provider_id, constructor_calls, search_calls, fetch_calls, closed):
    class Client:
        def __init__(self, *args, **kwargs):
            constructor_calls.append((provider_id, args, kwargs))

        async def search(self, *args, **kwargs):
            search_calls[provider_id] = (args, kwargs)
            url = (
                "https://www.youtube.com/watch?v=runtime-v20"
                if provider_id == "youtube"
                else f"https://example.test/{provider_id}"
            )
            return SearchResponse(
                query="runtime",
                source=provider_id,
                total_results=1,
                page=1,
                per_page=10,
                results=[
                    WebSearchResult(
                        source=provider_id,
                        title=f"{provider_id} runtime fixture",
                        url=url,
                        snippet="runtime",
                        engine=provider_id,
                    )
                ],
            )

        async def _fetch(self, method, *args, **kwargs):
            fetch_calls[provider_id] = (method, args, kwargs)
            target = (
                "https://deepwiki.com/owner/repo"
                if provider_id == "deepwiki"
                else "https://1.1.1.1/page"
            )
            return LegacyFetchResult(
                url=target,
                final_url=target,
                source=provider_id,
                title=f"{provider_id} runtime fixture",
                content="Runtime Fetch content " * 8,
                content_format="markdown",
            )

        async def contents(self, *args, **kwargs):
            return await self._fetch("contents", *args, **kwargs)

        async def extract(self, *args, **kwargs):
            return await self._fetch("extract", *args, **kwargs)

        async def fetch(self, *args, **kwargs):
            return await self._fetch("fetch", *args, **kwargs)

        async def reader(self, *args, **kwargs):
            return await self._fetch("reader", *args, **kwargs)

        async def scrape(self, *args, **kwargs):
            return await self._fetch("scrape", *args, **kwargs)

        async def close(self):
            closed[provider_id] += 1

    return Client


def _patch_fetch_validators(monkeypatch) -> None:
    for manifest, *_rest in runtime_module._BATCH_THREE_MULTI_BINDINGS:
        module = import_module(f"souwen.providers.information_sources.{manifest.id}.adapter")
        monkeypatch.setattr(module, "validate_fetch_url", lambda _url: (True, ""))
    for manifest, *_rest in runtime_module._BATCH_THREE_FETCH_ONLY_BINDINGS:
        module = import_module(f"souwen.providers.fetch_sources.{manifest.id}.adapter")
        if hasattr(module, "validate_fetch_url"):
            monkeypatch.setattr(module, "validate_fetch_url", lambda _url: (True, ""))


def test_every_batch_three_factory_dispatches_and_closes(monkeypatch) -> None:
    constructor_calls, search_calls, fetch_calls = [], {}, {}
    closed: Counter[str] = Counter()
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    _patch_fetch_validators(monkeypatch)
    for provider_id, global_name in _CLIENT_GLOBALS.items():
        monkeypatch.setattr(
            runtime_module,
            global_name,
            _fake_client(provider_id, constructor_calls, search_calls, fetch_calls, closed),
        )

    runtime = runtime_module.build_target_runtime(_configured())
    catalog = {item.provider: item for item in runtime.services.provider_items}
    assert len(catalog) == 65
    assert all(catalog[provider_id].availability == "available" for provider_id in _CLIENT_GLOBALS)

    async def exercise() -> None:
        for manifest, spec, *_rest in runtime_module._BATCH_THREE_SEARCH_ONLY_BINDINGS:
            page = await runtime.services.search.search(
                SearchRequest(
                    query="runtime",
                    domains=(spec.domain,),
                    providers=(ProviderRef(id=manifest.id, kind="search"),),
                ),
                RequestContext(request_id=f"batch-three-search-{manifest.id}"),
                ExecutionContext.with_timeout(5),
            )
            assert page.items
        for manifest, search_spec, *_rest in runtime_module._BATCH_THREE_MULTI_BINDINGS:
            page = await runtime.services.search.search(
                SearchRequest(
                    query="runtime",
                    domains=(search_spec.domain,),
                    providers=(ProviderRef(id=manifest.id, kind="search"),),
                ),
                RequestContext(request_id=f"batch-three-search-{manifest.id}"),
                ExecutionContext.with_timeout(5),
            )
            assert page.items

        fetch_manifests = [
            *(binding[0] for binding in runtime_module._BATCH_THREE_MULTI_BINDINGS),
            *(binding[0] for binding in runtime_module._BATCH_THREE_FETCH_ONLY_BINDINGS),
        ]
        for manifest in fetch_manifests:
            target = (
                "https://deepwiki.com/owner/repo"
                if manifest.id == "deepwiki"
                else "https://1.1.1.1/page"
            )
            batch = await runtime.services.fetch.fetch(
                FetchRequest(
                    targets=(target,),
                    providers=(ProviderRef(id=manifest.id, kind="fetch"),),
                ),
                RequestContext(request_id=f"batch-three-fetch-{manifest.id}"),
                ExecutionContext.with_timeout(5),
            )
            assert batch.items[0].status == "success"
            assert batch.items[0].provenance[0].provider == manifest.id
        await runtime.close()

    asyncio.run(exercise())
    assert set(search_calls) == {
        *(binding[0].id for binding in runtime_module._BATCH_THREE_SEARCH_ONLY_BINDINGS),
        *(binding[0].id for binding in runtime_module._BATCH_THREE_MULTI_BINDINGS),
    }
    assert search_calls["youtube"] == (
        ("runtime",),
        {"max_results": 10, "enrich": False},
    )
    assert all(
        call == (("runtime",), {"max_results": 10})
        for provider_id, call in search_calls.items()
        if provider_id != "youtube"
    )
    assert set(fetch_calls) == {
        *(binding[0].id for binding in runtime_module._BATCH_THREE_MULTI_BINDINGS),
        *(binding[0].id for binding in runtime_module._BATCH_THREE_FETCH_ONLY_BINDINGS),
    }
    target = "https://1.1.1.1/page"
    assert fetch_calls == {
        "apify": ("fetch", (target,), {"timeout": 30.0}),
        "cloudflare": ("fetch", (target,), {"timeout": 30.0}),
        "deepwiki": (
            "fetch",
            ("owner/repo",),
            {"max_depth": 0, "mode": "aggregate", "timeout": 30.0},
        ),
        "diffbot": ("fetch", (target,), {"timeout": 30.0}),
        "exa": ("contents", ([target],), {}),
        "firecrawl": ("scrape", (target,), {"timeout": 30.0}),
        "jina_reader": ("fetch", (target,), {"timeout": 30.0}),
        "kimi_code": ("fetch", (target,), {"timeout": 30.0}),
        "metaso": ("reader", (target,), {"timeout": 30.0}),
        "scraperapi": ("fetch", (target,), {"timeout": 30.0}),
        "scrapfly": ("fetch", (target,), {"timeout": 30.0}),
        "scrapingbee": ("fetch", (target,), {"timeout": 30.0}),
        "tavily": ("extract", ([target],), {"timeout": 30.0}),
        "wayback": ("fetch", (target,), {"timeout": 30.0}),
        "xcrawl": (
            "scrape",
            (target,),
            {"timeout": 30.0, "formats": None, "mode": "sync"},
        ),
        "zenrows": ("fetch", (target,), {"timeout": 30.0}),
    }
    constructed = Counter(provider_id for provider_id, _args, _kwargs in constructor_calls)
    assert constructed == Counter(
        {
            **{manifest.id: 1 for manifest in _batch_three_manifests()},
            **{manifest.id: 2 for manifest, *_rest in runtime_module._BATCH_THREE_MULTI_BINDINGS},
        }
    )
    assert closed == constructed


def test_batch_three_catalog_reports_every_required_field_without_values(monkeypatch) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(
        SouWenConfig(
            sources={manifest.id: {"enabled": True} for manifest in _batch_three_manifests()}
        )
    )
    catalog = {item.provider: item for item in runtime.services.provider_items}
    for manifest in _batch_three_manifests():
        expected = tuple(reference.lower() for reference in manifest.secrets.references)
        assert catalog[manifest.id].missing_fields == expected
        assert catalog[manifest.id].reason == ("missing_configuration" if expected else "available")
    assert "fixture" not in repr(runtime.services.provider_items)
    asyncio.run(runtime.close())


def test_every_real_batch_three_factory_constructs_probes_and_closes(monkeypatch) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(_configured())

    async def probe_and_close() -> None:
        expected_adapter_ids = {
            adapter.id for manifest in _batch_three_manifests() for adapter in manifest.adapters
        }
        for adapter_id in sorted(expected_adapter_ids):
            probe = await runtime.manager.probe(adapter_id, ExecutionContext.with_timeout(5))
            assert probe.status == "available"
        await runtime.close()

    asyncio.run(probe_and_close())


def test_batch_three_factories_ignore_undeclared_legacy_channel_overrides(monkeypatch) -> None:
    hostile = SouWenConfig(
        github_token="hostile-global-github-token",
        reddit_client_id="hostile-global-reddit-id",
        reddit_client_secret="hostile-global-reddit-secret",
        stackoverflow_api_key="hostile-global-stackoverflow-key",
        sources={
            "exa": {
                "base_url": "https://127.0.0.1:9443",
                "proxy": "http://127.0.0.1:8080",
                "headers": {"X-Undeclared": "hostile"},
            },
            "kimi_code": {
                "base_url": "https://127.0.0.1:9443",
                "params": {
                    "search_path": "/unreviewed/search",
                    "fetch_path": "/unreviewed/fetch",
                },
            },
            "wayback": {
                "base_url": "https://127.0.0.1:9443",
                "proxy": "http://127.0.0.1:8080",
                "headers": {"X-Undeclared": "hostile"},
                "http_backend": "httpx",
            },
        },
    )
    monkeypatch.setattr(http_client_module, "get_config", lambda: hostile)
    monkeypatch.setattr(scraper_base_module, "get_config", lambda: hostile)
    monkeypatch.setattr(github_module, "get_config", lambda: hostile)
    monkeypatch.setattr(kimi_code_module, "get_config", lambda: hostile)
    monkeypatch.setattr(reddit_module, "get_config", lambda: hostile)
    monkeypatch.setattr(stackoverflow_module, "get_config", lambda: hostile)
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(_configured(include_optional=False))

    async def construct_and_close() -> None:
        for adapter_id in (
            "exa-search",
            "github-search",
            "kimi_code-search",
            "reddit-search",
            "stackoverflow-search",
            "wayback-fetch",
        ):
            assert (
                await runtime.manager.probe(adapter_id, ExecutionContext.with_timeout(5))
            ).status == "available"

        exa = runtime.manager._runtimes["exa-search"].instance._client._client
        github = runtime.manager._runtimes["github-search"].instance._client._client
        kimi = runtime.manager._runtimes["kimi_code-search"].instance._client._client
        reddit = runtime.manager._runtimes["reddit-search"].instance._client._client
        stackoverflow = runtime.manager._runtimes["stackoverflow-search"].instance._client._client
        wayback = runtime.manager._runtimes["wayback-fetch"].instance._client._client
        assert exa.base_url == "https://api.exa.ai"
        assert "X-Undeclared" not in exa._client.headers
        assert kimi.base_url == "https://api.kimi.com"
        assert kimi._params == {}
        assert github.token == ""
        assert reddit._client_id == "" and reddit._client_secret == ""
        assert reddit._oauth_mode is False
        assert stackoverflow.api_key == ""
        assert wayback._resolved_base_url == "https://web.archive.org"
        assert wayback._proxy is None
        assert wayback._channel_headers == {}
        assert source_channel_overrides_enabled() is True
        await runtime.close()

    asyncio.run(construct_and_close())


def test_batch_three_admits_proxy_only_when_manifest_supports_it(monkeypatch) -> None:
    reviewed_proxy = "http://192.0.2.10:8080"
    transport_options = {}

    def capture_transport(_self, **kwargs):
        transport_options.update(kwargs)

    monkeypatch.setattr(http_client_module.HttpTransport, "__init__", capture_transport)
    with without_source_channel_overrides(proxy=reviewed_proxy):
        http_client_module.SouWenHttpClient(
            base_url="https://api.example.test",
            source_name="fixture",
        )
    assert transport_options["proxy"] == reviewed_proxy
    assert transport_options["base_url"] == "https://api.example.test"

    observed = []

    class Apify:
        def __init__(self, api_token):
            observed.append((api_token, reviewed_source_proxy()))

        async def close(self):
            return None

    monkeypatch.setattr(runtime_module, "ApifyClient", Apify)
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = runtime_module.build_target_runtime(
        _configured(source_overrides={"apify": {"proxy": reviewed_proxy}})
    )

    async def construct_and_close() -> None:
        assert (
            await runtime.manager.probe("apify-fetch", ExecutionContext.with_timeout(5))
        ).status == "available"
        await runtime.close()

    asyncio.run(construct_and_close())
    assert observed == [("fixture-apify_api_token", reviewed_proxy)]
    assert reviewed_source_proxy() is None
