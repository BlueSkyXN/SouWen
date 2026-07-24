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


class _BrowserExecutor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.targets = []

    async def fetch(self, request, request_context, execution):
        self.targets.append(request.target)
        if self.fail:
            raise ProviderError(ProviderErrorCode.WORKER_OVERLOADED)
        content = "browser rendered canonical content " * 4
        return FetchResult(
            target=request.target,
            final_url=request.target,
            status="success",
            content=content,
            content_metadata=ContentMetadata(
                media_type="text/html",
                retrieved_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
                truncated=False,
                quality="high",
            ),
            provenance=(Provenance(provider="builtin-fetch", attempt=2, outcome="success"),),
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


@pytest.mark.asyncio
async def test_module_uses_browser_as_execution_fallback_not_another_provider() -> None:
    browser = _BrowserExecutor()
    service = FetchModuleService(_Manager(), browser_executor=browser)

    batch = await service.fetch(
        FetchRequest(targets=("https://example.com/short",)),
        RequestContext(request_id="fetch-browser-fallback"),
        ExecutionContext.with_timeout(5),
    )

    assert batch.items[0].content_metadata.quality == "high"
    assert [item.provider for item in batch.items[0].provenance] == [
        "builtin-fetch",
        "builtin-fetch",
    ]
    assert batch.items[0].provenance[1].attempt == 2
    assert browser.targets == [batch.items[0].target]
    assert batch.meta.partial is False


@pytest.mark.asyncio
async def test_browser_failure_keeps_low_quality_builtin_partial() -> None:
    browser = _BrowserExecutor(fail=True)
    batch = await FetchModuleService(_Manager(), browser_executor=browser).fetch(
        FetchRequest(targets=("https://example.com/short",)),
        RequestContext(request_id="fetch-browser-fallback"),
        ExecutionContext.with_timeout(5),
    )

    assert batch.items[0].content == "short"
    assert batch.items[0].content_metadata.quality == "low"
    assert [item.outcome for item in batch.items[0].provenance] == ["success", "failed"]
    assert batch.meta.partial is True
