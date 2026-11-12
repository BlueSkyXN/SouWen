"""Target-runtime integration for the retained Batch 6 self-hosted providers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from souwen.common_runtime.channel_overrides import (
    reviewed_source_max_retries,
    reviewed_source_proxy,
    reviewed_source_timeout_seconds,
    source_channel_overrides_enabled,
)
from souwen.providers.runtime_clients.models import WebSearchResponse, WebSearchResult


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


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    (("souwen.providers.runtime_clients.web.searxng", "SearXNGClient"),),
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
