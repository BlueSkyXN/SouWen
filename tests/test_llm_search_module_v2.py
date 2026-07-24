"""Deterministic orchestration tests for the canonical LLM Search module."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from souwen.modules.llm_search.application import LLMSearchModuleService
from souwen.platform.provider_spi import (
    EvidenceItem,
    ExecutionContext,
    LLMSearchRequest,
    LLMSearchResult,
    ProviderError,
    ProviderErrorCode,
    ProviderRef,
    Provenance,
    RequestContext,
    SearchItem,
    SearchMeta,
    Usage,
)


ADAPTER_ID = "uniapi_ark_annotations_deepseek_v3_2_251201"


class _Manager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, adapter_id, request, request_context, execution):
        self.calls.append(adapter_id)
        retrieved_at = datetime(2026, 7, 24, tzinfo=timezone.utc)
        item = SearchItem(
            id="url:fixture",
            title="Fixture",
            url="https://example.com/fixture",
            rank=1,
            provenance=(
                Provenance(
                    provider=adapter_id,
                    outcome="success",
                    retrieved_at=retrieved_at,
                ),
            ),
        )
        return LLMSearchResult(
            query=request.query,
            items=(item,),
            evidence=(
                EvidenceItem(
                    id="evidence:fixture",
                    item_id=item.id,
                    provider=adapter_id,
                    public_url="https://example.com/fixture",
                    title_or_snippet="Fixture",
                    retrieved_at=retrieved_at,
                ),
            ),
            meta=SearchMeta(requested=(adapter_id,), succeeded=(adapter_id,)),
            usage=Usage(),
            context=request_context,
        )


def _request(*, provider_id: str = ADAPTER_ID, strategy: str = "single") -> LLMSearchRequest:
    return LLMSearchRequest(
        query="query",
        providers=(ProviderRef(id=provider_id, kind="llm_search"),),
        strategy=strategy,
    )


@pytest.mark.asyncio
async def test_module_executes_only_the_deployment_configured_adapter() -> None:
    manager = _Manager()
    result = await LLMSearchModuleService(manager, ADAPTER_ID).search(
        _request(),
        RequestContext(request_id="module-v2"),
        ExecutionContext.with_timeout(5),
    )

    assert result.query == "query"
    assert manager.calls == [ADAPTER_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "canonical_request",
    [
        _request(provider_id="uniapi_ark_annotations_doubao_seed_2_0_lite_260428"),
        _request(strategy="fanout"),
    ],
)
async def test_module_rejects_request_side_source_or_strategy_override(
    canonical_request: LLMSearchRequest,
) -> None:
    manager = _Manager()
    with pytest.raises(ProviderError) as caught:
        await LLMSearchModuleService(manager, ADAPTER_ID).search(
            canonical_request,
            RequestContext(request_id="module-v2"),
            ExecutionContext.with_timeout(5),
        )

    assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
    assert manager.calls == []


@pytest.mark.asyncio
async def test_module_honours_cancellation_before_provider_dispatch() -> None:
    manager = _Manager()
    execution = ExecutionContext.with_timeout(5)
    execution.cancel_event.set()

    with pytest.raises(ProviderError) as caught:
        await LLMSearchModuleService(manager, ADAPTER_ID).search(
            _request(),
            RequestContext(request_id="module-v2"),
            execution,
        )

    assert caught.value.code is ProviderErrorCode.CANCELLED
    assert manager.calls == []
