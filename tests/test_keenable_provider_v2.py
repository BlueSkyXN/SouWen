from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchRequest,
)
from souwen.providers.information_sources.keenable import (
    KEENABLE_PROVIDER_MANIFEST,
    KEENABLE_PROVIDER_SPEC,
    KeenableSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response, self.calls = response, []

    async def search(self, query: str, max_results: int = 10) -> object:
        self.calls.append((query, max_results))
        return self.response


def test_keenable_manifest_and_spec_agree() -> None:
    assert KEENABLE_PROVIDER_SPEC.auth.reference == "KEENABLE_API_KEY"
    assert KEENABLE_PROVIDER_SPEC.auth.required is True
    assert KEENABLE_PROVIDER_MANIFEST.id == "keenable"
    assert KEENABLE_PROVIDER_SPEC.transport.host == "api.keenable.ai"


@pytest.mark.asyncio
async def test_keenable_maps_legacy_result_and_rejects_invalid_upstream() -> None:
    response = SearchResponse(
        query="query",
        source="keenable",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="keenable",
                title="Result",
                url="https://example.test/path?x=1#fragment",
                snippet="summary",
                engine="keenable",
            )
        ],
    )
    client = _Client(response)
    page = await KeenableSearchProvider(client).search(
        SearchRequest(query="query", domains=("web",)),
        RequestContext(request_id="keenable"),
        ExecutionContext.with_timeout(5),
    )
    assert client.calls == [("query", 10)]
    assert str(page.items[0].url) == "https://example.test/path?x=1"
    with pytest.raises(ProviderError) as caught:
        await KeenableSearchProvider(_Client(object())).search(
            SearchRequest(query="bad", domains=("web",)),
            RequestContext(request_id="keenable-bad"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE


@pytest.mark.asyncio
async def test_keenable_client_posts_query_and_maps_description_then_snippet(monkeypatch) -> None:
    from souwen.providers.runtime_clients.web.keenable import KeenableClient

    calls: list[tuple[str, dict]] = []

    class _Resp:
        def json(self) -> dict:
            return {
                "results": [
                    {"title": "A", "url": "https://a.example/", "description": "d", "snippet": "s"},
                    {
                        "title": "B",
                        "url": "https://b.example/",
                        "description": "",
                        "snippet": "x" * 900,
                    },
                    {"title": "no url"},
                ]
            }

    async def fake_post(self, path: str, json: dict, **kwargs) -> _Resp:
        calls.append((path, json))
        return _Resp()

    monkeypatch.setattr(KeenableClient, "post", fake_post)
    client = KeenableClient(api_key="kn-key")
    response = await client.search("query", max_results=5)
    assert calls == [("/v1/search", {"query": "query", "max_results": 5})]
    assert [(r.url, r.snippet) for r in response.results] == [
        ("https://a.example/", "d"),
        ("https://b.example/", "x" * 500),
    ]
    assert response.source == "keenable"
