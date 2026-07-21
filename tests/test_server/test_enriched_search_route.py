"""HTTP contract tests for the additive enriched web-search route."""

from __future__ import annotations

import asyncio
import threading

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not installed", allow_module_level=True)

from souwen.models import EnrichedWebSearchResult, SearchSnippet, SearchSourceProvenance
from souwen.web.enriched_search import (
    EnrichedSearchDeadlineExceeded,
    EnrichedSearchExecution,
    EnrichedSearchSourceDisabledError,
    EnrichedSearchSourceValidationError,
    EnrichedSearchUnavailableError,
    EnrichedSearchUnknownSourceError,
    EnrichedSourceAttempt,
)

SOURCE = "uniapi_ark_annotations_deepseek_v3_2_251201"


@pytest.fixture(autouse=True)
def isolated_search_limiter(monkeypatch):
    """Keep route-contract assertions independent of earlier server requests."""
    from souwen.server import limiter as limiter_mod

    monkeypatch.setattr(
        limiter_mod,
        "_search_limiter",
        limiter_mod.InMemoryRateLimiter(max_requests=60, window_seconds=60),
    )


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Keep auth/config isolation equivalent to the server integration suite."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SOUWEN_PLUGIN_AUTOLOAD", "0")
    for key in ("SOUWEN_USER_PASSWORD", "SOUWEN_ADMIN_PASSWORD", "SOUWEN_EDITION"):
        monkeypatch.delenv(key, raising=False)
    from souwen.config import get_config

    get_config.cache_clear()
    from souwen.server.app import app

    yield TestClient(app, raise_server_exceptions=False)
    get_config.cache_clear()


def _execution(*, outcome: str = "success_with_results", partial: bool = False):
    attempts = (
        EnrichedSourceAttempt(SOURCE, 1, outcome),
        EnrichedSourceAttempt("other", 2, "failed"),
    )
    outcomes = {SOURCE: outcome, "other": "failed"}
    if not partial:
        attempts = attempts[:1]
        outcomes = {SOURCE: outcome}
    return EnrichedSearchExecution(
        query="test query",
        results=[
            EnrichedWebSearchResult(
                result_id="R1",
                rank=1,
                title="Verified title",
                url="https://example.com/article",
                canonical_url="https://example.com/article",
                site_domain="example.com",
                discoveries=[
                    SearchSourceProvenance(
                        source_id=SOURCE,
                        scheme_id="uniapi_ark_annotations_v1",
                        gateway_id="uniapi",
                        requested_model_id="deepseek-v3-2-251201",
                    )
                ],
                fetch_status="not_requested",
            )
        ],
        source_outcomes=outcomes,
        discarded_candidates=0,
        source_attempts=attempts,
        visible_search_calls=1,
        provider_metered_search_calls=None,
    )


def _request_payload(**overrides):
    payload = {
        "query": "test query",
        "sources": [SOURCE],
        "source_strategy": "single",
        "fetch": {"enabled": False},
        "budget": {"max_total_seconds": 1, "max_source_attempts": 1},
    }
    payload.update(overrides)
    return payload


def test_enriched_route_returns_typed_partial_response_without_provider_raw(client, monkeypatch):
    async def fake_enriched(*args, **kwargs):
        assert args == ("test query",)
        assert kwargs["sources"] == [SOURCE]
        assert kwargs["source_strategy"] == "single"
        assert kwargs["fetch"] is False
        return _execution(partial=True)

    monkeypatch.setattr("souwen.web.enriched_search.enriched_web_search", fake_enriched)

    response = client.post("/api/v1/search/web/enriched", json=_request_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "test query"
    assert data["results"][0]["title"] == "Verified title"
    assert data["meta"]["partial"] is True
    assert data["meta"]["source_outcomes"] == {SOURCE: "success_with_results", "other": "failed"}
    assert data["meta"]["provider_metered_search_calls"] is None
    assert data["usage"]["search_tool_cost"] is None
    assert "raw" not in data["results"][0]
    assert "api_key" not in str(data)
    assert "base_url" not in str(data)


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (EnrichedSearchUnknownSourceError("unknown"), 422),
        (EnrichedSearchSourceValidationError("not concrete"), 422),
        (EnrichedSearchSourceDisabledError("disabled"), 409),
        (EnrichedSearchUnavailableError("unavailable"), 502),
        (EnrichedSearchDeadlineExceeded("deadline"), 504),
    ],
)
def test_enriched_route_maps_safe_source_failures(client, monkeypatch, error, status):
    async def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("souwen.web.enriched_search.enriched_web_search", fail)

    response = client.post("/api/v1/search/web/enriched", json=_request_payload())

    assert response.status_code == status
    assert "api_key" not in response.text
    assert "base_url" not in response.text


def test_enriched_route_rejects_dynamic_model_and_single_source_violations(client):
    invalid_model = client.post(
        "/api/v1/search/web/enriched",
        json=_request_payload(model="arbitrary-model"),
    )
    invalid_strategy = client.post(
        "/api/v1/search/web/enriched",
        json=_request_payload(
            sources=[SOURCE, "uniapi_ark_annotations_doubao_seed_2_0_lite_260428"]
        ),
    )

    assert invalid_model.status_code == 422
    assert invalid_strategy.status_code == 422


def test_enriched_route_projects_synthesis_and_never_accepts_request_model(client, monkeypatch):
    from souwen.llm.models import EnrichedSynthesisAnswer, LLMUsage

    async def fake_enriched(*_args, **kwargs):
        assert kwargs["synthesis_profile"] == "safe"
        execution = _execution()
        result = execution.results[0].model_copy(
            update={
                "summary": SearchSnippet(
                    text="Generated summary", type="generated", model="served-model"
                )
            }
        )
        return EnrichedSearchExecution(
            query=execution.query,
            results=[result],
            source_outcomes=execution.source_outcomes,
            discarded_candidates=execution.discarded_candidates,
            source_attempts=execution.source_attempts,
            visible_search_calls=execution.visible_search_calls,
            synthesis_status="success",
            answer=EnrichedSynthesisAnswer(
                text="Generated answer [R1]",
                citations=["R1"],
                profile="safe",
                model="served-model",
                protocol="openai_chat",
            ),
            summary_usage=LLMUsage(prompt_tokens=12, completion_tokens=8, total_tokens=20),
        )

    monkeypatch.setattr("souwen.web.enriched_search.enriched_web_search", fake_enriched)
    response = client.post(
        "/api/v1/search/web/enriched", json=_request_payload(synthesis={"profile": "safe"})
    )

    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["summary"]["type"] == "generated"
    assert data["answer"] == {
        "text": "Generated answer [R1]",
        "citations": ["R1"],
        "profile": "safe",
        "model": "served-model",
        "protocol": "openai_chat",
    }
    assert data["meta"]["synthesis_status"] == "success"
    assert data["meta"]["summarized_pages"] == 1
    assert data["usage"]["summary_input_tokens"] == 12
    assert data["usage"]["summary_output_tokens"] == 8

    rejected = client.post(
        "/api/v1/search/web/enriched",
        json=_request_payload(synthesis={"profile": "safe", "model": "arbitrary"}),
    )
    assert rejected.status_code == 422


def test_enriched_route_uses_existing_search_auth_dependency(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SOUWEN_USER_PASSWORD", "test-user-password")
    from souwen.config import get_config

    get_config.cache_clear()
    from souwen.server.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/v1/search/web/enriched", json=_request_payload())

    assert response.status_code == 401
    get_config.cache_clear()


def test_enriched_route_cancels_the_pending_execution_at_endpoint_deadline(client, monkeypatch):
    cancelled = threading.Event()

    async def slow(*_args, **_kwargs):
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()

    monkeypatch.setattr("souwen.web.enriched_search.enriched_web_search", slow)

    response = client.post("/api/v1/search/web/enriched", json=_request_payload())

    assert response.status_code == 504
    assert cancelled.is_set()
