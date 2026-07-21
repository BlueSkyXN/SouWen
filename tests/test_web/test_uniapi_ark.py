"""Deterministic Ark annotation contract tests; no UniAPI request is sent."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from souwen.config import LLMSearchGatewayConfig, SouWenConfig, SourceChannelConfig
from souwen.core.exceptions import ConfigError
from souwen.models import SearchSourceProvenance
from souwen.registry import get
from souwen.web.llm_search.schemes.ark_annotations import (
    ARK_ANNOTATIONS_DEEPSEEK,
    ARK_ANNOTATIONS_DOUBAO,
    UniApiArkAnnotationsDeepSeekClient,
    UniApiArkAnnotationsDoubaoClient,
    build_ark_request,
    parse_ark_annotations,
)
from souwen.web.search import web_search


def _provenance() -> SearchSourceProvenance:
    return SearchSourceProvenance(
        source_id="ark_fixture",
        scheme_id="uniapi_ark_annotations_v1",
        gateway_id="uniapi",
        upstream_channel="volcengine_ark",
        requested_model_id="fixture",
        protocol="responses",
        tool_schema="ark_web_search_v1",
    )


def _payload(
    *,
    status: str = "completed",
    reason: str | None = None,
    annotations: list[dict] | None = None,
    include_search_call: bool = True,
    include_message: bool = True,
    message_status: str = "completed",
) -> dict:
    output: list[dict] = []
    if include_search_call:
        output.append({"type": "web_search_call", "status": "completed"})
    if include_message:
        output.append(
            {
                "type": "message",
                "status": message_status,
                "message": {"content": [{"annotations": annotations or []}]},
            }
        )
    result = {"status": status, "model": "served-fixture-model", "output": output}
    if reason is not None:
        result["reason"] = reason
    return result


def _configure_source(monkeypatch, source_id: str, *, params: dict | None = None) -> SouWenConfig:
    config = SouWenConfig(
        edition="full",
        llm_search_gateways={
            "uniapi": LLMSearchGatewayConfig(
                api_key="fixture-api-key",
                base_url="https://gateway.example.test/v1",
            )
        },
        sources={source_id: SourceChannelConfig(enabled=True, params=params or {})},
    )
    monkeypatch.setattr("souwen.web.llm_search.schemes.ark_annotations.get_config", lambda: config)
    monkeypatch.setattr("souwen.core.http_client.get_config", lambda: config)
    return config


def test_ark_parser_uses_only_completed_structured_annotations() -> None:
    payload = _payload(
        annotations=[
            {
                "type": "url_citation",
                "title": "Real title",
                "url": "https://example.com/a",
                "summary": "Provider summary",
                "site_name": "Example",
                "publish_time": "2026-07-20T00:00:00Z",
                "logo_url": "https://example.com/favicon.ico",
            }
        ]
    )

    candidates = parse_ark_annotations(payload, _provenance())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Real title"
    assert candidate.url == "https://example.com/a"
    assert candidate.provider_snippet is not None
    assert candidate.provider_snippet.type == "provider_summary"
    assert candidate.site_name == "Example"
    assert candidate.published_at == "2026-07-20T00:00:00Z"
    assert candidate.favicon_url == "https://example.com/favicon.ico"
    assert candidate.provenance.served_model_id == "served-fixture-model"
    assert candidate.provenance.search_call_status == "completed"
    assert candidate.provenance.response_status == "completed"
    assert candidate.provenance.partial is False


def test_ark_parser_accepts_valid_annotations_from_incomplete_doubao_receipt() -> None:
    candidates = parse_ark_annotations(
        _payload(
            status="incomplete",
            reason="length",
            message_status="incomplete",
            annotations=[
                {
                    "type": "url_citation",
                    "title": "Usable source",
                    "url": "https://example.com/usable",
                }
            ],
        ),
        _provenance(),
    )

    provenance = candidates[0].provenance
    assert provenance.partial is True
    assert provenance.response_status == "incomplete"
    assert provenance.incomplete_reason == "length"


@pytest.mark.parametrize(
    "payload",
    [
        _payload(include_search_call=False),
        _payload(annotations=[]),
        _payload(
            annotations=[
                {"type": "url_citation", "title": "", "url": "https://example.com/empty"},
                {"type": "url_citation", "title": "Unsafe", "url": "file:///private/data"},
            ]
        ),
        {
            "status": "completed",
            "output": [
                {"type": "web_search_call", "status": "completed"},
                {
                    "type": "message",
                    "status": "completed",
                    "content": [{"annotations": [{"title": "Wrong nesting", "url": "https://x"}]}],
                },
            ],
        },
    ],
)
def test_ark_parser_fails_closed_for_missing_or_invalid_search_evidence(payload: dict) -> None:
    with pytest.raises(ValueError, match="Ark response has no"):
        parse_ark_annotations(payload, _provenance())


def test_ark_parser_never_extracts_urls_from_final_answer_text() -> None:
    payload = _payload(annotations=[])
    payload["output"].append(
        {
            "type": "message",
            "status": "completed",
            "message": {
                "content": [
                    {
                        "type": "output_text",
                        "text": "Invented answer: https://not-a-structured-source.example/",
                    }
                ]
            },
        }
    )

    with pytest.raises(ValueError, match="Ark response has no"):
        parse_ark_annotations(payload, _provenance())


def test_ark_request_binds_model_and_tool_shape() -> None:
    assert build_ark_request("q", "model", max_keyword=2) == {
        "model": "model",
        "input": "q",
        "tools": [{"type": "web_search", "max_keyword": 2}],
    }


def test_ark_concrete_sources_are_projected_as_experimental_opt_in_sources() -> None:
    for spec in (ARK_ANNOTATIONS_DEEPSEEK, ARK_ANNOTATIONS_DOUBAO):
        adapter = get(spec.source_id)
        assert adapter is not None
        assert adapter.llm_search_identity == (spec.scheme_id, spec.model_id)
        assert adapter.default_enabled is False
        assert adapter.runtime_default_enabled is False
        assert adapter.default_for == frozenset()
        assert adapter.stability == "experimental"
        assert adapter.methods["search"].timeout_seconds == 45.0
        assert spec.last_verified_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_class", "spec"),
    [
        (UniApiArkAnnotationsDeepSeekClient, ARK_ANNOTATIONS_DEEPSEEK),
        (UniApiArkAnnotationsDoubaoClient, ARK_ANNOTATIONS_DOUBAO),
    ],
)
async def test_each_ark_source_makes_one_bound_single_attempt_request(
    monkeypatch, client_class, spec
) -> None:
    _configure_source(monkeypatch, spec.source_id, params={"max_keyword": 2})
    client = client_class()
    client.post = AsyncMock(
        return_value=httpx.Response(
            200,
            json=_payload(
                annotations=[
                    {
                        "type": "url_citation",
                        "title": "First",
                        "url": "https://example.com/first",
                    },
                    {
                        "type": "url_citation",
                        "title": "Duplicate",
                        "url": "https://example.com/first/",
                    },
                    {
                        "type": "url_citation",
                        "title": "Second",
                        "url": "https://example.com/second",
                    },
                ]
            ),
        )
    )
    try:
        receipt = await client.search_candidate_receipt("search query", max_results=1)
    finally:
        await client.close()

    candidates = list(receipt.candidates)
    assert [candidate.url for candidate in candidates] == ["https://example.com/first"]
    assert receipt.visible_search_calls == 1
    assert receipt.provider_metered_search_calls is None
    assert receipt.tool_call_types == ("web_search_call",)
    assert receipt.valid_annotation_count == 3
    assert receipt.response_status == "completed"
    assert receipt.input_tokens is None
    assert receipt.output_tokens is None
    assert receipt.total_tokens is None
    client.post.assert_awaited_once_with(
        "/v1/responses",
        json={
            "model": spec.model_id,
            "input": "search query",
            "tools": [{"type": "web_search", "max_keyword": 2}],
        },
        retry_policy="single_attempt",
    )
    assert candidates[0].provenance.source_id == spec.source_id
    assert candidates[0].provenance.requested_model_id == spec.model_id


@pytest.mark.asyncio
async def test_ark_legacy_search_projection_keeps_candidate_provenance(monkeypatch) -> None:
    _configure_source(monkeypatch, ARK_ANNOTATIONS_DEEPSEEK.source_id)
    client = UniApiArkAnnotationsDeepSeekClient()
    client.post = AsyncMock(
        return_value=httpx.Response(
            200,
            json=_payload(
                annotations=[
                    {
                        "type": "url_citation",
                        "title": "Structured source",
                        "url": "https://example.com/source",
                        "summary": "summary",
                    }
                ]
            ),
        )
    )
    try:
        response = await client.search("query")
    finally:
        await client.close()

    result = response.results[0]
    assert result.source == ARK_ANNOTATIONS_DEEPSEEK.source_id
    assert result.raw["search_candidate"]["provenance"]["source_id"] == (
        ARK_ANNOTATIONS_DEEPSEEK.source_id
    )
    assert result.raw["search_candidate"]["provenance"]["requested_model_id"] == (
        ARK_ANNOTATIONS_DEEPSEEK.model_id
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_class", "spec"),
    [
        (UniApiArkAnnotationsDeepSeekClient, ARK_ANNOTATIONS_DEEPSEEK),
        (UniApiArkAnnotationsDoubaoClient, ARK_ANNOTATIONS_DOUBAO),
    ],
)
async def test_web_search_dispatches_only_the_explicit_bound_ark_source(
    monkeypatch, client_class, spec
) -> None:
    config = _configure_source(monkeypatch, spec.source_id)
    monkeypatch.setattr("souwen.web.search.get_config", lambda: config)
    requests: list[dict] = []

    async def fake_post(_self, path, *, json, retry_policy):
        requests.append({"path": path, "json": json, "retry_policy": retry_policy})
        return httpx.Response(
            200,
            json=_payload(
                annotations=[
                    {
                        "type": "url_citation",
                        "title": "Selected source result",
                        "url": "https://example.com/selected",
                    }
                ]
            ),
        )

    monkeypatch.setattr(client_class, "post", fake_post)
    response = await web_search("query", engines=[spec.source_id])

    assert [result.source for result in response.results] == [spec.source_id]
    assert requests == [
        {
            "path": "/v1/responses",
            "json": {
                "model": spec.model_id,
                "input": "query",
                "tools": [{"type": "web_search", "max_keyword": 10}],
            },
            "retry_policy": "single_attempt",
        }
    ]


def test_ark_client_requires_shared_gateway_fields(monkeypatch) -> None:
    config = SouWenConfig(
        edition="full",
        sources={ARK_ANNOTATIONS_DEEPSEEK.source_id: SourceChannelConfig(enabled=True)},
    )
    monkeypatch.setattr("souwen.web.llm_search.schemes.ark_annotations.get_config", lambda: config)

    with pytest.raises(ConfigError, match="llm_search_gateways.uniapi.api_key"):
        UniApiArkAnnotationsDeepSeekClient()
