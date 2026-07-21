from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from souwen.models import (
    FetchResponse,
    FetchResult,
    SearchCandidate,
    SearchSnippet,
    SearchSourceProvenance,
    WebSearchResponse,
    WebSearchResult,
)
from souwen.web.enriched_search import (
    EnrichedSearchSourceDisabledError,
    EnrichedSearchSourceValidationError,
    EnrichedSearchUnknownSourceError,
    _validate_concrete_sources,
    enriched_web_search,
)


@pytest.mark.asyncio
async def test_enriched_search_applies_successful_synthesis_without_discarding_fetch_evidence(
    monkeypatch,
):
    from souwen.config.models import LLMSynthesisProfile
    from souwen.llm.enriched_synthesis import EnrichedSynthesisResult
    from souwen.llm.models import EnrichedSynthesisAnswer, LLMUsage

    async def fake_search(*_args, **_kwargs):
        return WebSearchResponse(
            query="q",
            source="one",
            results=[
                WebSearchResult(
                    source="one", engine="one", title="Title", url="https://example.com/article"
                )
            ],
        )

    async def fake_fetch(urls, **_kwargs):
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url=urls[0],
                    final_url=urls[0],
                    title="Fetched title",
                    content="Fetched evidence",
                    source="builtin",
                )
            ],
        )

    profile = LLMSynthesisProfile(
        protocol="openai_chat",
        model="configured-model",
        max_tokens=100,
        max_input_chars=1000,
        max_pages=1,
        timeout=10,
    )

    async def fake_synthesize(results, **kwargs):
        assert kwargs["profile_id"] == "safe"
        assert [result.result_id for result in results] == ["R1"]
        return EnrichedSynthesisResult(
            summaries={
                "R1": SearchSnippet(
                    text="Generated summary", type="generated", model="served-model"
                )
            },
            answer=EnrichedSynthesisAnswer(
                text="Generated answer [R1]",
                citations=["R1"],
                profile="safe",
                model="served-model",
                protocol="openai_chat",
            ),
            usage=LLMUsage(prompt_tokens=4, completion_tokens=3, total_tokens=7),
        )

    monkeypatch.setattr("souwen.web.enriched_search.web_search", fake_search)
    monkeypatch.setattr("souwen.web.enriched_search.fetch_content", fake_fetch)
    monkeypatch.setattr(
        "souwen.web.enriched_search.resolve_enriched_synthesis_profile", lambda _: profile
    )
    monkeypatch.setattr("souwen.web.enriched_search.synthesize_enriched_results", fake_synthesize)

    execution = await enriched_web_search("q", engines="one", synthesis_profile="safe")

    assert execution.synthesis_status == "success"
    assert execution.results[0].summary is not None
    assert execution.results[0].summary.text == "Generated summary"
    assert execution.answer is not None
    assert execution.answer.citations == ["R1"]
    assert execution.summary_usage is not None
    assert execution.summary_usage.completion_tokens == 3


@pytest.mark.asyncio
async def test_enriched_search_preserves_results_when_optional_synthesis_fails(monkeypatch, caplog):
    from souwen.config.models import LLMSynthesisProfile

    async def fake_search(*_args, **_kwargs):
        return WebSearchResponse(
            query="q",
            source="one",
            results=[
                WebSearchResult(
                    source="one", engine="one", title="Title", url="https://example.com/article"
                )
            ],
        )

    async def fake_fetch(urls, **_kwargs):
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url=urls[0], final_url=urls[0], title="Fetched title", content="Evidence"
                )
            ],
        )

    profile = LLMSynthesisProfile(
        protocol="openai_chat",
        model="configured-model",
        max_tokens=100,
        max_input_chars=1000,
        max_pages=1,
        timeout=10,
    )

    async def failed_synthesis(*_args, **_kwargs):
        raise RuntimeError("api_key=secret-value provider failure")

    monkeypatch.setattr("souwen.web.enriched_search.web_search", fake_search)
    monkeypatch.setattr("souwen.web.enriched_search.fetch_content", fake_fetch)
    monkeypatch.setattr(
        "souwen.web.enriched_search.resolve_enriched_synthesis_profile", lambda _: profile
    )
    monkeypatch.setattr("souwen.web.enriched_search.synthesize_enriched_results", failed_synthesis)

    execution = await enriched_web_search("q", engines="one", synthesis_profile="safe")

    assert execution.synthesis_status == "failed"
    assert [result.title for result in execution.results] == ["Title"]
    assert execution.answer is None
    assert "secret-value" not in caplog.text


@pytest.mark.asyncio
async def test_enriched_search_skips_synthesis_before_model_call_after_shared_deadline(monkeypatch):
    from souwen.config.models import LLMSynthesisProfile

    class DeadlineAfterFetch:
        def __init__(self, *_args, **_kwargs):
            self.calls = 0

        def timeout_for(self, requested_seconds):
            self.calls += 1
            if self.calls == 1:
                return requested_seconds
            raise TimeoutError("deadline exhausted")

    async def fake_search(*_args, **_kwargs):
        return WebSearchResponse(
            query="q",
            source="one",
            results=[
                WebSearchResult(
                    source="one", engine="one", title="Title", url="https://example.com/article"
                )
            ],
        )

    async def fake_fetch(urls, **_kwargs):
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url=urls[0], final_url=urls[0], title="Fetched title", content="Evidence"
                )
            ],
        )

    profile = LLMSynthesisProfile(
        protocol="openai_chat",
        model="configured-model",
        max_tokens=100,
        max_input_chars=1000,
        max_pages=1,
        timeout=10,
    )
    model_call = AsyncMock()
    monkeypatch.setattr("souwen.web.enriched_search.SearchDeadlineBudget", DeadlineAfterFetch)
    monkeypatch.setattr("souwen.web.enriched_search.web_search", fake_search)
    monkeypatch.setattr("souwen.web.enriched_search.fetch_content", fake_fetch)
    monkeypatch.setattr(
        "souwen.web.enriched_search.resolve_enriched_synthesis_profile", lambda _: profile
    )
    monkeypatch.setattr("souwen.web.enriched_search.synthesize_enriched_results", model_call)

    execution = await enriched_web_search("q", engines="one", synthesis_profile="safe")

    assert execution.synthesis_status == "skipped"
    assert execution.results
    model_call.assert_not_awaited()


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
async def test_enriched_search_preserves_real_urls_when_deduplication_is_disabled(monkeypatch):
    async def fake_search(*_args, **_kwargs):
        return WebSearchResponse(
            query="q",
            source="one",
            results=[
                WebSearchResult(
                    source="one", engine="one", title="First", url="https://example.com/a"
                ),
                WebSearchResult(
                    source="two", engine="two", title="Second", url="https://example.com/a"
                ),
            ],
        )

    monkeypatch.setattr("souwen.web.enriched_search.web_search", fake_search)

    execution = await enriched_web_search(
        "q", engines=["one", "two"], deduplicate=False, fetch=False
    )

    assert [result.url for result in execution.results] == [
        "https://example.com/a",
        "https://example.com/a",
    ]
    assert [result.canonical_url for result in execution.results] == [
        "https://example.com/a",
        "https://example.com/a",
    ]


@pytest.mark.asyncio
async def test_enriched_search_fanout_fetch_matches_results_by_discovery_url(monkeypatch):
    async def fake_search(*_args, **_kwargs):
        return WebSearchResponse(
            query="q",
            source="one",
            results=[
                WebSearchResult(
                    source="one", engine="one", title="One", url="https://example.com/one"
                ),
                WebSearchResult(
                    source="one", engine="one", title="Two", url="https://example.com/two"
                ),
            ],
        )

    async def fake_fetch(urls, **_kwargs):
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url="https://example.com/one",
                    final_url="https://example.com/one",
                    source="first",
                    error="first failed",
                ),
                FetchResult(
                    url="https://example.com/two",
                    final_url="https://example.com/two",
                    source="first",
                    content="first content",
                ),
                FetchResult(
                    url="https://example.com/one",
                    final_url="https://example.com/one",
                    source="second",
                    content="second content",
                ),
                FetchResult(
                    url="https://example.com/two",
                    final_url="https://example.com/two",
                    source="second",
                    error="second failed",
                ),
            ],
        )

    monkeypatch.setattr("souwen.web.enriched_search.web_search", fake_search)
    monkeypatch.setattr("souwen.web.enriched_search.fetch_content", fake_fetch)

    execution = await enriched_web_search(
        "q",
        engines="one",
        fetch_strategy="fanout",
        fetch_providers=["first", "second"],
        include_content=True,
    )

    by_url = {result.url: result for result in execution.results}
    assert execution.fetched_pages == 2
    assert by_url["https://example.com/one"].fetch_provider == "second"
    assert by_url["https://example.com/one"].content == "second content"
    assert by_url["https://example.com/two"].fetch_provider == "first"
    assert by_url["https://example.com/two"].content == "first content"


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
                provider_metered_search_calls=1,
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
    assert execution.provider_metered_search_calls is None
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


def test_enriched_search_rejects_missing_required_credentials_before_client_import(monkeypatch):
    adapter = SimpleNamespace(
        llm_search_identity=("test_scheme_v1", "test-model"),
        capabilities=frozenset({"search"}),
        runtime_default_enabled=True,
        config_field="api_key",
        credential_fields=("api_key",),
        auth_requirement="required",
    )
    config = SimpleNamespace(
        edition="full",
        is_source_enabled=lambda *_args, **_kwargs: True,
        resolve_api_key=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr("souwen.web.enriched_search.get_config", lambda: config)
    monkeypatch.setattr("souwen.web.enriched_search.get_source_adapter", lambda _source: adapter)
    monkeypatch.setattr("souwen.web.enriched_search.ensure_source_allowed", lambda *_args: None)

    with pytest.raises(EnrichedSearchSourceValidationError, match="缺少必需配置"):
        _validate_concrete_sources(["test_source"])


@pytest.mark.asyncio
async def test_enriched_search_honors_configured_source_timeout_before_shared_deadline(monkeypatch):
    seen_timeouts: list[float] = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def search_candidate_receipt(self, *_args, **_kwargs):
            return SimpleNamespace(
                candidates=(
                    SearchCandidate(
                        title="Configured timeout",
                        url="https://example.com/configured-timeout",
                        provenance=SearchSourceProvenance(
                            source_id="one", scheme_id="test_scheme_v1"
                        ),
                    ),
                ),
                visible_search_calls=1,
                provider_metered_search_calls=None,
            )

    adapter = SimpleNamespace(
        client_loader=lambda: Client,
        methods={"search": SimpleNamespace(timeout_seconds=10.0)},
    )
    config = SimpleNamespace(get_source_config=lambda _source: SimpleNamespace(timeout=75.0))

    async def fake_wait_for(awaitable, *, timeout):
        seen_timeouts.append(timeout)
        return await awaitable

    monkeypatch.setattr(
        "souwen.web.enriched_search._validate_concrete_sources", lambda _sources: [("one", adapter)]
    )
    monkeypatch.setattr("souwen.web.enriched_search.get_config", lambda: config)
    monkeypatch.setattr("souwen.web.enriched_search.asyncio.wait_for", fake_wait_for)

    execution = await enriched_web_search(
        "q",
        sources=["one"],
        source_strategy="single",
        deadline_seconds=120,
        fetch=False,
    )

    assert execution.results[0].title == "Configured timeout"
    assert seen_timeouts == [75.0]
