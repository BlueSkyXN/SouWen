"""Provider v2 conformance for the immutable UniAPI Ark adapters."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from souwen.platform.provider_spi import (
    ExecutionContext,
    LLMSearchRequest,
    ProviderError,
    ProviderErrorCode,
    ProviderRef,
    RequestContext,
)
from souwen.providers.llm_sources.uniapi_ark_annotations.adapter import (
    UniApiArkAnnotationsDeepSeekProvider,
    UniApiArkAnnotationsDoubaoProvider,
)
from souwen.providers.llm_sources.uniapi_ark_annotations.manifest import (
    DEEPSEEK_ADAPTER_ID,
    DOUBAO_ADAPTER_ID,
    UNIAPI_ARK_DEEPSEEK_MANIFEST,
    UNIAPI_ARK_DOUBAO_MANIFEST,
)
from souwen.web.llm_search.schemes.ark_annotations import (
    ARK_ANNOTATIONS_DEEPSEEK,
    ARK_ANNOTATIONS_DOUBAO,
)


class _Response:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _Transport:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []
        self.closed = 0

    async def post(self, url, json=None, data=None, headers=None, retry_policy="default"):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "data": data,
                "headers": headers,
                "retry_policy": retry_policy,
            }
        )
        return _Response(self.payload)

    async def close(self) -> None:
        self.closed += 1


class _BlockingTransport(_Transport):
    async def post(self, *args, **kwargs):
        await asyncio.Event().wait()


def _payload(
    model_id: str,
    *,
    annotations: list[dict[str, Any]] | None = None,
    include_search_call: bool = True,
    usage: Any = None,
) -> dict[str, Any]:
    output: list[dict[str, Any]] = []
    if include_search_call:
        output.append({"type": "web_search_call", "status": "completed"})
    output.append(
        {
            "type": "message",
            "status": "completed",
            "message": {
                "content": [
                    {
                        "type": "output_text",
                        "text": "Untrusted answer https://must-not-be-inferred.example/",
                        "annotations": annotations or [],
                    }
                ]
            },
        }
    )
    return {
        "status": "completed",
        "model": model_id,
        "output": output,
        "usage": usage,
    }


def _provider(provider_type, payload):
    transport = _Transport(payload)
    provider = provider_type(
        {"enabled": True, "max_keyword": 10, "timeout_seconds": 45},
        {
            "UNIAPI_API_KEY": "fixture-secret",
            "UNIAPI_BASE_URL": "https://gateway.example.test",
        },
        transport=transport,
        clock=lambda: datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    return provider, transport


def _request(adapter_id: str, *, max_results: int | None = None) -> LLMSearchRequest:
    return LLMSearchRequest(
        query="  canonical query  ",
        providers=(ProviderRef(id=adapter_id, kind="llm_search"),),
        strategy="single",
        max_results_per_provider=max_results,
    )


def test_manifests_match_legacy_immutable_source_and_model_identities() -> None:
    pairs = (
        (
            UNIAPI_ARK_DEEPSEEK_MANIFEST,
            ARK_ANNOTATIONS_DEEPSEEK,
            UniApiArkAnnotationsDeepSeekProvider,
        ),
        (
            UNIAPI_ARK_DOUBAO_MANIFEST,
            ARK_ANNOTATIONS_DOUBAO,
            UniApiArkAnnotationsDoubaoProvider,
        ),
    )
    for manifest, legacy, provider_type in pairs:
        assert manifest.version == "2.0.0rc2"
        assert manifest.id == legacy.source_id == provider_type.ADAPTER_ID
        assert provider_type.MODEL_ID == legacy.model_id
        assert manifest.adapters[0].availability == "configured"
        assert manifest.secrets.references == ("UNIAPI_API_KEY", "UNIAPI_BASE_URL")
        assert manifest.network.egress_hosts == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_type", "adapter_id", "model_id"),
    [
        (
            UniApiArkAnnotationsDeepSeekProvider,
            DEEPSEEK_ADAPTER_ID,
            "deepseek-v3-2-251201",
        ),
        (
            UniApiArkAnnotationsDoubaoProvider,
            DOUBAO_ADAPTER_ID,
            "doubao-seed-2-0-lite-260428",
        ),
    ],
)
async def test_each_adapter_executes_one_bound_request_and_emits_evidence_usage(
    provider_type, adapter_id: str, model_id: str
) -> None:
    provider, transport = _provider(
        provider_type,
        _payload(
            model_id,
            annotations=[
                {
                    "type": "url_citation",
                    "title": "Structured source",
                    "url": "https://example.com/source",
                    "summary": "Provider-reported summary",
                },
                {
                    "type": "url_citation",
                    "title": "Duplicate",
                    "url": "https://example.com/source#fragment",
                },
            ],
            usage={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
        ),
    )
    result = await provider.search(
        _request(adapter_id, max_results=2),
        RequestContext(request_id="provider-v2"),
        ExecutionContext.with_timeout(5),
    )

    assert result.answer is None
    assert len(result.items) == len(result.evidence) == 1
    assert result.evidence[0].item_id == result.items[0].id
    assert result.evidence[0].provider == adapter_id
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.usage.cost is None
    assert transport.calls == [
        {
            "url": "/v1/responses",
            "json": {
                "model": model_id,
                "input": "canonical query",
                "tools": [{"type": "web_search", "max_keyword": 2}],
            },
            "data": None,
            "headers": None,
            "retry_policy": "single_attempt",
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        _payload("deepseek-v3-2-251201", annotations=[]),
        _payload(
            "deepseek-v3-2-251201",
            annotations=[
                {
                    "type": "url_citation",
                    "title": "Private literal",
                    "url": "http://127.0.0.1/private",
                }
            ],
        ),
        _payload(
            "deepseek-v3-2-251201",
            annotations=[
                {
                    "type": "url_citation",
                    "title": "Unsafe scheme",
                    "url": "file:///private/data",
                }
            ],
        ),
        _payload(
            "deepseek-v3-2-251201",
            annotations=[
                {
                    "type": "url_citation",
                    "title": "Structured",
                    "url": "https://example.com/source",
                }
            ],
            include_search_call=False,
        ),
        _payload(
            "unexpected-model",
            annotations=[
                {
                    "type": "url_citation",
                    "title": "Structured",
                    "url": "https://example.com/source",
                }
            ],
        ),
    ],
)
async def test_provider_fails_closed_without_valid_structured_public_evidence(payload) -> None:
    provider, _transport = _provider(UniApiArkAnnotationsDeepSeekProvider, payload)

    with pytest.raises(ProviderError) as caught:
        await provider.search(
            _request(DEEPSEEK_ADAPTER_ID),
            RequestContext(request_id="provider-v2"),
            ExecutionContext.with_timeout(5),
        )

    assert caught.value.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
    assert "must-not-be-inferred" not in str(caught.value)


@pytest.mark.asyncio
async def test_provider_rejects_request_identity_and_hidden_workflow_overrides() -> None:
    provider, transport = _provider(
        UniApiArkAnnotationsDeepSeekProvider,
        _payload("deepseek-v3-2-251201"),
    )
    wrong_source = _request(DOUBAO_ADAPTER_ID)
    fetch_request = _request(DEEPSEEK_ADAPTER_ID).model_copy(update={"fetch": {"enabled": True}})

    for request in (wrong_source, fetch_request):
        with pytest.raises(ProviderError) as caught:
            await provider.search(
                request,
                RequestContext(request_id="provider-v2"),
                ExecutionContext.with_timeout(5),
            )
        assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert transport.calls == []


@pytest.mark.asyncio
async def test_provider_live_cancellation_closes_the_pending_gateway_call() -> None:
    transport = _BlockingTransport({})
    provider = UniApiArkAnnotationsDeepSeekProvider(
        {"enabled": True},
        {
            "UNIAPI_API_KEY": "fixture-secret",
            "UNIAPI_BASE_URL": "https://gateway.example.test",
        },
        transport=transport,
    )
    execution = ExecutionContext.with_timeout(5)
    task = asyncio.create_task(
        provider.search(
            _request(DEEPSEEK_ADAPTER_ID),
            RequestContext(request_id="provider-v2"),
            execution,
        )
    )
    await asyncio.sleep(0)
    execution.cancel_event.set()

    with pytest.raises(ProviderError) as caught:
        await task
    assert caught.value.code is ProviderErrorCode.CANCELLED


@pytest.mark.asyncio
async def test_probe_is_local_and_close_is_idempotent() -> None:
    provider, transport = _provider(
        UniApiArkAnnotationsDeepSeekProvider,
        _payload("deepseek-v3-2-251201"),
    )
    assert (await provider.probe(ExecutionContext.with_timeout(5))).status == "available"
    assert transport.calls == []

    await provider.close()
    await provider.close()

    assert transport.closed == 1
    assert (await provider.probe(ExecutionContext.with_timeout(5))).status == "unavailable"
