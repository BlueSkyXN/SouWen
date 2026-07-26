from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import SearchResponse, WebSearchResult
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPageRequest,
    SearchRequest,
)
from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.information_sources.youtube import (
    YOUTUBE_PROVIDER_MANIFEST,
    YOUTUBE_PROVIDER_SPEC,
    YouTubeSearchProvider,
)


class _Client:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls = []

    async def search(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


def test_youtube_manifest_spec():
    assert (
        validate_spec_manifest(YOUTUBE_PROVIDER_SPEC, YOUTUBE_PROVIDER_MANIFEST)
        is YOUTUBE_PROVIDER_SPEC
    )


def _response(url: str) -> SearchResponse:
    return SearchResponse(
        query="video",
        source="youtube",
        total_results=1,
        page=1,
        per_page=10,
        results=[
            WebSearchResult(
                source="youtube",
                title="Canonical video",
                url=url,
                engine="youtube",
            )
        ],
    )


@pytest.mark.asyncio
async def test_youtube_search_disables_enrichment_and_uses_canonical_video_identity() -> None:
    client = _Client(_response("https://www.youtube.com/watch?v=provider-v2"))
    page = await YouTubeSearchProvider(client).search(
        SearchRequest(
            query="video",
            domains=("videos",),
            page=SearchPageRequest(limit=5),
        ),
        RequestContext(request_id="youtube"),
        ExecutionContext.with_timeout(5),
    )

    assert client.calls == [(("video",), {"max_results": 5, "enrich": False})]
    assert str(page.items[0].url) == "https://www.youtube.com/watch?v=provider-v2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?list=provider-v2",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=provider-v2&list=playlist",
        "https://user@www.youtube.com/watch?v=provider-v2",
        "https://www.youtube.com:444/watch?v=provider-v2",
        "https://www.youtube.com/watch?v=provider-v2#fragment",
    ],
)
async def test_youtube_search_rejects_noncanonical_video_urls(url: str) -> None:
    with pytest.raises(ProviderError) as caught:
        await YouTubeSearchProvider(_Client(_response(url))).search(
            SearchRequest(query="video", domains=("videos",)),
            RequestContext(request_id="youtube-invalid"),
            ExecutionContext.with_timeout(5),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
