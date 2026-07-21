from __future__ import annotations

import pytest

from souwen.models import FetchResponse, FetchResult, WebSearchResponse, WebSearchResult
from souwen.web.enriched_search import enriched_web_search


@pytest.mark.asyncio
async def test_enriched_search_merges_discovery_and_uses_fetch_title(monkeypatch):
    async def fake_search(*_args, **_kwargs):
        return WebSearchResponse(
            query="q",
            source="one",
            results=[
                WebSearchResult(source="one", engine="one", title="", url="https://example.com/a"),
                WebSearchResult(
                    source="two", engine="two", title="Second", url="https://example.com/a#x"
                ),
            ],
        )

    async def fake_fetch(urls, **_kwargs):
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url="https://example.com/a",
                    final_url="https://example.com/a",
                    title="Fetched title",
                    content="Fetched body text",
                    source="builtin",
                )
            ],
        )

    monkeypatch.setattr("souwen.web.enriched_search.web_search", fake_search)
    monkeypatch.setattr("souwen.web.enriched_search.fetch_content", fake_fetch)
    execution = await enriched_web_search("q", engines=["one", "two"], include_content=True)

    assert execution.source_outcomes == {
        "one": "success_with_results",
        "two": "success_with_results",
    }
    assert len(execution.results) == 1
    result = execution.results[0]
    assert result.title == "Fetched title"
    assert [item.source_id for item in result.discoveries] == ["one", "two"]
    assert result.content == "Fetched body text"
    assert result.content_excerpt is not None


@pytest.mark.asyncio
async def test_enriched_search_discards_url_only_candidate_when_fetch_fails(monkeypatch):
    async def fake_search(*_args, **_kwargs):
        return WebSearchResponse(
            query="q",
            source="one",
            results=[
                WebSearchResult(source="one", engine="one", title="", url="https://example.com/a")
            ],
        )

    async def fake_fetch(urls, **_kwargs):
        return FetchResponse(
            urls=list(urls), results=[FetchResult(url=urls[0], final_url=urls[0], error="failed")]
        )

    monkeypatch.setattr("souwen.web.enriched_search.web_search", fake_search)
    monkeypatch.setattr("souwen.web.enriched_search.fetch_content", fake_fetch)
    execution = await enriched_web_search("q", engines="one")

    assert execution.results == []
    assert execution.discarded_candidates == 1
