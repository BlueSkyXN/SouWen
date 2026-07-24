"""Canonical Fetch Module batch and partial-result behavior."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from souwen.modules.fetch.application import FetchModuleService
from souwen.platform.provider_spi import (
    ContentMetadata,
    ExecutionContext,
    FetchRequest,
    FetchResult,
    ProviderError,
    ProviderErrorCode,
    ProviderRef,
    Provenance,
    RequestContext,
)


class _Manager:
    async def execute(self, adapter_id, request, request_context, execution):
        if "blocked" in str(request.target):
            raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id=adapter_id)
        content = (
            "short" if "short" in str(request.target) else "long enough canonical content " * 4
        )
        return FetchResult(
            target=request.target,
            final_url=request.target,
            status="success",
            content=content,
            content_metadata=ContentMetadata(
                media_type="text/plain",
                retrieved_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
                truncated=False,
                quality="low" if len(content) <= 63 else "high",
            ),
            provenance=(Provenance(provider=adapter_id, outcome="success"),),
        )


@pytest.mark.asyncio
async def test_module_keeps_order_and_marks_low_or_failed_items_partial() -> None:
    context = RequestContext(request_id="fetch-module-v2")
    batch = await FetchModuleService(_Manager()).fetch(
        FetchRequest(
            targets=(
                "https://example.com/long",
                "https://example.com/short",
                "https://example.com/blocked",
            )
        ),
        context,
        ExecutionContext.with_timeout(5),
    )

    assert [item.status for item in batch.items] == ["success", "success", "blocked"]
    assert batch.items[1].content_metadata.quality == "low"
    assert batch.items[2].error.code == "policy_blocked"
    assert batch.meta.partial is True
    assert batch.context == context


@pytest.mark.asyncio
async def test_module_rejects_request_side_provider_or_fanout_override() -> None:
    service = FetchModuleService(_Manager())
    context = RequestContext(request_id="fetch-module-v2")
    for request in (
        FetchRequest(targets=("https://example.com",), strategy="fanout"),
        FetchRequest(
            targets=("https://example.com",),
            providers=(ProviderRef(id="other", kind="fetch"),),
        ),
    ):
        with pytest.raises(ProviderError) as caught:
            await service.fetch(request, context, ExecutionContext.with_timeout(5))
        assert caught.value.code is ProviderErrorCode.INVALID_REQUEST
