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
        provider_id = (
            adapter_id if adapter_id == "builtin-fetch" else adapter_id.removesuffix("-fetch")
        )
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
            provenance=(Provenance(provider=provider_id, outcome="success"),),
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


class _RecordingManager(_Manager):
    def __init__(self) -> None:
        self.adapter_ids = []

    async def execute(self, adapter_id, request, request_context, execution):
        self.adapter_ids.append(adapter_id)
        return await super().execute(adapter_id, request, request_context, execution)


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
async def test_module_rejects_unknown_or_non_fetch_provider_override() -> None:
    service = FetchModuleService(_Manager())
    context = RequestContext(request_id="fetch-module-v2")
    for request in (
        FetchRequest(
            targets=("https://example.com",),
            providers=(ProviderRef(id="other", kind="fetch"),),
        ),
        FetchRequest(
            targets=("https://example.com",),
            providers=(ProviderRef(id="other", kind="search"),),
        ),
    ):
        with pytest.raises(ProviderError) as caught:
            await service.fetch(request, context, ExecutionContext.with_timeout(5))
        assert caught.value.code is ProviderErrorCode.INVALID_REQUEST


@pytest.mark.asyncio
async def test_module_fanout_returns_one_outcome_per_target_and_provider() -> None:
    manager = _RecordingManager()
    service = FetchModuleService(
        manager,
        provider_adapter_ids={"other": "other-fetch"},
    )

    batch = await service.fetch(
        FetchRequest(
            targets=("https://example.com/one", "https://example.com/two"),
            providers=(
                ProviderRef(id="builtin-fetch", kind="fetch"),
                ProviderRef(id="other", kind="fetch"),
            ),
            strategy="fanout",
        ),
        RequestContext(request_id="fetch-fanout"),
        ExecutionContext.with_timeout(5),
    )

    assert manager.adapter_ids == [
        "builtin-fetch",
        "other-fetch",
        "builtin-fetch",
        "other-fetch",
    ]
    assert [str(item.target) for item in batch.items] == [
        "https://example.com/one",
        "https://example.com/one",
        "https://example.com/two",
        "https://example.com/two",
    ]
    assert [item.provenance[0].provider for item in batch.items] == [
        "builtin-fetch",
        "other",
        "builtin-fetch",
        "other",
    ]


@pytest.mark.asyncio
async def test_module_fallback_advances_after_failure_and_stops_after_success() -> None:
    class Manager(_RecordingManager):
        async def execute(self, adapter_id, request, request_context, execution):
            self.adapter_ids.append(adapter_id)
            if adapter_id == "first-fetch":
                raise ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)
            return await _Manager.execute(self, adapter_id, request, request_context, execution)

    manager = Manager()
    service = FetchModuleService(
        manager,
        provider_adapter_ids={
            "first": "first-fetch",
            "second": "second-fetch",
            "third": "third-fetch",
        },
    )

    batch = await service.fetch(
        FetchRequest(
            targets=("https://example.com/one",),
            providers=(
                ProviderRef(id="first", kind="fetch"),
                ProviderRef(id="second", kind="fetch"),
                ProviderRef(id="third", kind="fetch"),
            ),
            strategy="fallback",
        ),
        RequestContext(request_id="fetch-fallback"),
        ExecutionContext.with_timeout(5),
    )

    assert manager.adapter_ids == ["first-fetch", "second-fetch"]
    assert batch.items[0].status == "success"
    assert [item.provider for item in batch.items[0].provenance] == [
        "first",
        "second",
    ]


@pytest.mark.asyncio
async def test_fanout_failure_uses_public_provider_identity() -> None:
    class Manager(_RecordingManager):
        async def execute(self, adapter_id, request, request_context, execution):
            self.adapter_ids.append(adapter_id)
            if adapter_id == "newspaper-fetch":
                raise ProviderError(
                    ProviderErrorCode.RATE_LIMITED,
                    provider_id="newspaper",
                    retry_after_seconds=11,
                )
            return await _Manager.execute(self, adapter_id, request, request_context, execution)

    batch = await FetchModuleService(
        Manager(),
        provider_adapter_ids={
            "newspaper": "newspaper-fetch",
            "other": "other-fetch",
        },
    ).fetch(
        FetchRequest(
            targets=("https://example.com/one",),
            providers=(
                ProviderRef(id="newspaper", kind="fetch"),
                ProviderRef(id="other", kind="fetch"),
            ),
            strategy="fanout",
        ),
        RequestContext(request_id="fetch-public-provider-id"),
        ExecutionContext.with_timeout(5),
    )

    failed = batch.items[0]
    assert failed.status == "failed"
    assert failed.provenance[0].provider == "newspaper"
    assert failed.error.provider == "newspaper"
    assert batch.items[1].status == "success"
    assert batch.meta.partial is True


@pytest.mark.asyncio
async def test_single_provider_failure_preserves_public_identity_and_retry_metadata() -> None:
    class Manager:
        async def execute(self, adapter_id, request, request_context, execution):
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id="newspaper",
                retry_after_seconds=17,
            )

    service = FetchModuleService(
        Manager(),
        provider_adapter_ids={"newspaper": "newspaper-fetch"},
    )

    with pytest.raises(ProviderError) as caught:
        await service.fetch(
            FetchRequest(
                targets=("https://example.com/one",),
                providers=(ProviderRef(id="newspaper", kind="fetch"),),
            ),
            RequestContext(request_id="fetch-public-provider-error"),
            ExecutionContext.with_timeout(5),
        )

    assert caught.value.code is ProviderErrorCode.RATE_LIMITED
    assert caught.value.provider_id == "newspaper"
    assert caught.value.retry_after_seconds == 17


@pytest.mark.asyncio
async def test_fallback_keeps_low_quality_candidate_after_fatal_later_attempt() -> None:
    class Manager(_RecordingManager):
        async def execute(self, adapter_id, request, request_context, execution):
            self.adapter_ids.append(adapter_id)
            if adapter_id == "second-fetch":
                raise ProviderError(
                    ProviderErrorCode.POLICY_BLOCKED,
                    provider_id="second",
                )
            return await _Manager.execute(self, adapter_id, request, request_context, execution)

    manager = Manager()
    batch = await FetchModuleService(
        manager,
        provider_adapter_ids={
            "first": "first-fetch",
            "second": "second-fetch",
            "third": "third-fetch",
        },
    ).fetch(
        FetchRequest(
            targets=("https://example.com/short",),
            providers=(
                ProviderRef(id="first", kind="fetch"),
                ProviderRef(id="second", kind="fetch"),
                ProviderRef(id="third", kind="fetch"),
            ),
            strategy="fallback",
        ),
        RequestContext(request_id="fetch-low-quality-fatal"),
        ExecutionContext.with_timeout(5),
    )

    assert manager.adapter_ids == ["first-fetch", "second-fetch"]
    assert batch.items[0].status == "success"
    assert batch.items[0].content == "short"
    assert batch.items[0].content_metadata.quality == "low"
    assert [item.provider for item in batch.items[0].provenance] == ["first", "second"]
    assert [item.outcome for item in batch.items[0].provenance] == ["success", "failed"]
    assert batch.meta.partial is True


@pytest.mark.asyncio
async def test_module_dispatches_an_explicit_fetch_provider_without_builtin_browser_fallback() -> (
    None
):
    manager = _RecordingManager()
    browser = _BrowserExecutor()
    service = FetchModuleService(
        manager,
        provider_adapter_ids={"arxiv_fulltext": "arxiv_fulltext-fetch"},
        browser_executor=browser,
    )

    batch = await service.fetch(
        FetchRequest(
            targets=("https://arxiv.org/abs/2601.00001?short",),
            providers=(ProviderRef(id="arxiv_fulltext", kind="fetch"),),
        ),
        RequestContext(request_id="fetch-explicit-provider"),
        ExecutionContext.with_timeout(5),
    )

    assert manager.adapter_ids == ["arxiv_fulltext-fetch"]
    assert batch.items[0].content_metadata.quality == "low"
    assert browser.targets == []


@pytest.mark.asyncio
async def test_module_raises_canonical_error_when_every_target_fails() -> None:
    service = FetchModuleService(_Manager())

    with pytest.raises(ProviderError) as caught:
        await service.fetch(
            FetchRequest(
                targets=(
                    "https://example.com/blocked-one",
                    "https://example.com/blocked-two",
                )
            ),
            RequestContext(request_id="fetch-all-failed"),
            ExecutionContext.with_timeout(5),
        )

    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED


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
