from __future__ import annotations

from types import SimpleNamespace

import pytest

from souwen.models import (
    FetchResponse,
    FetchResult,
    SearchCandidate,
    SearchSourceProvenance,
    WebSearchResponse,
    WebSearchResult,
)
from souwen.web.enriched_search import (
    EnrichedSearchSourceDisabledError,
    EnrichedSearchUnknownSourceError,
    _validate_concrete_sources,
    enriched_web_search,
)


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


@pytest.mark.asyncio
async def test_enriched_search_fanout_preserves_partial_source_outcomes(monkeypatch):
    class SuccessfulClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def search_candidate_receipt(self, *_args, **_kwargs):
            return SimpleNamespace(
                candidates=(
                    SearchCandidate(
                        title="Structured title",
                        url="https://example.com/article",
                        provenance=SearchSourceProvenance(
                            source_id="one",
                            scheme_id="test_scheme_v1",
                        ),
                    ),
                ),
                visible_search_calls=1,
                provider_metered_search_calls=None,
            )

    class FailingClient:
        async def __aenter__(self):
            raise RuntimeError("provider failed")

        async def __aexit__(self, *_args):
            return None

    adapters = [
        (
            "one",
            SimpleNamespace(
                client_loader=lambda: SuccessfulClient,
                methods={"search": SimpleNamespace(timeout_seconds=1.0)},
            ),
        ),
        (
            "two",
            SimpleNamespace(
                client_loader=lambda: FailingClient,
                methods={"search": SimpleNamespace(timeout_seconds=1.0)},
            ),
        ),
    ]
    monkeypatch.setattr(
        "souwen.web.enriched_search._validate_concrete_sources", lambda _sources: adapters
    )

    execution = await enriched_web_search(
        "q",
        sources=["one", "two"],
        source_strategy="fanout",
        max_source_attempts=2,
        deadline_seconds=5,
        fetch=False,
    )

    assert execution.source_outcomes == {"one": "success_with_results", "two": "failed"}
    assert execution.partial is True
    assert execution.visible_search_calls == 1
    assert execution.results[0].discoveries[0].source_strategy == "fanout"
    assert execution.results[0].discoveries[0].attempt_index == 1


@pytest.mark.asyncio
async def test_enriched_search_first_success_stops_after_first_result_source(monkeypatch):
    class SuccessfulClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def search_candidate_receipt(self, *_args, **_kwargs):
            return SimpleNamespace(
                candidates=(
                    SearchCandidate(
                        title="First result",
                        url="https://example.com/first",
                        provenance=SearchSourceProvenance(
                            source_id="one",
                            scheme_id="test_scheme_v1",
                        ),
                    ),
                ),
                visible_search_calls=1,
                provider_metered_search_calls=None,
            )

    def unexpected_loader():
        raise AssertionError("first_success must not load the next source after a result")

    adapters = [
        (
            "one",
            SimpleNamespace(
                client_loader=lambda: SuccessfulClient,
                methods={"search": SimpleNamespace(timeout_seconds=1.0)},
            ),
        ),
        (
            "two",
            SimpleNamespace(
                client_loader=unexpected_loader,
                methods={"search": SimpleNamespace(timeout_seconds=1.0)},
            ),
        ),
    ]
    monkeypatch.setattr(
        "souwen.web.enriched_search._validate_concrete_sources", lambda _sources: adapters
    )

    execution = await enriched_web_search(
        "q",
        sources=["one", "two"],
        source_strategy="first_success",
        max_source_attempts=2,
        deadline_seconds=5,
        fetch=False,
    )

    assert execution.source_outcomes == {"one": "success_with_results"}
    assert [attempt.source_id for attempt in execution.source_attempts] == ["one"]
    assert execution.results[0].discoveries[0].source_strategy == "first_success"


def test_enriched_search_rejects_unknown_and_default_disabled_concrete_sources(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from souwen.config import get_config

    get_config.cache_clear()
    with pytest.raises(EnrichedSearchUnknownSourceError):
        _validate_concrete_sources(["not_registered"])

    with pytest.raises(EnrichedSearchSourceDisabledError):
        _validate_concrete_sources(["uniapi_ark_annotations_deepseek_v3_2_251201"])
    get_config.cache_clear()


def test_enriched_search_checks_edition_before_default_disabled_source(monkeypatch):
    from souwen.editions import EditionError

    config = SimpleNamespace(edition="basic", is_source_enabled=lambda *_args, **_kwargs: True)
    monkeypatch.setattr("souwen.web.enriched_search.get_config", lambda: config)

    with pytest.raises(EditionError):
        _validate_concrete_sources(["uniapi_ark_annotations_deepseek_v3_2_251201"])
