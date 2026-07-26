"""Deterministic request and projection coverage for Batch 6 legacy clients."""

from __future__ import annotations

import httpx
import pytest

from souwen.providers.runtime_clients.web.searxng import SearXNGClient
from souwen.providers.runtime_clients.web.websurfx import WebsurfxClient
from souwen.providers.runtime_clients.web.whoogle import WhoogleClient


async def _install_transport(client, handler) -> None:
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url=client.instance_url,
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )


@pytest.mark.asyncio
async def test_searxng_uses_json_search_endpoint_and_projects_engine() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "number_of_results": 2,
                "results": [
                    {
                        "title": "SearXNG result",
                        "url": "https://example.test/searxng",
                        "content": "snippet",
                        "engine": "google",
                    },
                    {
                        "title": "Second result",
                        "url": "https://example.test/second",
                    },
                ],
            },
        )

    client = SearXNGClient("http://127.0.0.1:8888", follow_redirects=False)
    await _install_transport(client, handler)
    try:
        response = await client.search("provider v2", max_results=1)
    finally:
        await client.close()

    assert len(requests) == 1
    assert requests[0].url.path == "/search"
    assert requests[0].url.params["q"] == "provider v2"
    assert requests[0].url.params["format"] == "json"
    assert requests[0].url.params["language"] == "auto"
    assert response.total_results == 2
    assert [(item.title, item.engine) for item in response.results] == [
        ("SearXNG result", "google")
    ]


@pytest.mark.asyncio
async def test_websurfx_uses_json_search_endpoint_and_description_fallback() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Description result",
                        "url": "https://example.test/description",
                        "description": "preferred",
                        "content": "fallback",
                    },
                    {
                        "title": "Content result",
                        "url": "https://example.test/content",
                        "content": "fallback",
                    },
                ]
            },
        )

    client = WebsurfxClient("https://websurfx.internal", follow_redirects=False)
    await _install_transport(client, handler)
    try:
        response = await client.search("provider v2")
    finally:
        await client.close()

    assert len(requests) == 1
    assert requests[0].url.path == "/search"
    assert dict(requests[0].url.params) == {"q": "provider v2", "format": "json"}
    assert [item.snippet for item in response.results] == ["preferred", "fallback"]


@pytest.mark.asyncio
async def test_whoogle_uses_html_search_endpoint_and_selector_fallback() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text="""
            <html><body><div class="g">
              <a href="https://example.test/whoogle"><h3>Whoogle result</h3></a>
              <div class="BNeawe s3v9rd">Whoogle snippet</div>
            </div></body></html>
            """,
        )

    client = WhoogleClient("http://whoogle.internal:5000", follow_redirects=False)
    await _install_transport(client, handler)
    try:
        response = await client.search("provider v2")
    finally:
        await client.close()

    assert len(requests) == 1
    assert requests[0].url.path == "/search"
    assert dict(requests[0].url.params) == {"q": "provider v2"}
    assert [(item.title, item.url, item.snippet) for item in response.results] == [
        ("Whoogle result", "https://example.test/whoogle", "Whoogle snippet")
    ]
