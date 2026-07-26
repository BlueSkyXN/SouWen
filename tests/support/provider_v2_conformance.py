"""Reusable deterministic Provider v2 conformance cases.

Provider-specific tests own request and response mappings.  This harness owns
the stable lifecycle, failure, cancellation, and redaction contract so adding a
migrated Search Provider without all nine cases fails closed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

import pytest

from souwen.common_runtime.transport.errors import RateLimitError
from souwen.platform.provider_spi import (
    ExecutionContext,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
    SearchPage,
    SearchRequest,
)


SEARCH_CONFORMANCE_CASES = (
    "success",
    "empty",
    "invalid_config",
    "cancellation",
    "rate_limit",
    "invalid_upstream",
    "policy_blocked",
    "probe_close",
    "redaction",
)


class ScriptedSearchClient:
    """Capability-shaped fake client with no network or environment access."""

    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.close_count = 0
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def search(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.outcome is BLOCK:
            self.entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    async def close(self) -> None:
        self.close_count += 1


BLOCK = object()


@dataclass(frozen=True, slots=True)
class SearchConformanceDefinition:
    """Provider-owned mapping inputs consumed by the common nine-case harness."""

    provider_id: str
    build_provider: Callable[[ScriptedSearchClient, bool], Any]
    request: SearchRequest
    success_response: Any
    empty_response: Any
    invalid_response: Any


async def run_search_conformance_case(
    definition: SearchConformanceDefinition,
    case_id: str,
) -> None:
    """Run one stable case against one Search Provider declaration."""
    if case_id not in SEARCH_CONFORMANCE_CASES:
        raise AssertionError(f"unknown Provider v2 conformance case: {case_id}")

    context = RequestContext(
        request_id=f"conformance-{definition.provider_id}-{case_id}",
    )

    if case_id in {"success", "empty"}:
        response = (
            definition.success_response if case_id == "success" else definition.empty_response
        )
        client = ScriptedSearchClient(response)
        page = await definition.build_provider(client, True).search(
            definition.request,
            context,
            ExecutionContext.with_timeout(5),
        )
        assert isinstance(page, SearchPage)
        assert page.context == context
        assert page.meta.requested == (definition.provider_id,)
        assert page.meta.succeeded == (definition.provider_id,)
        assert not page.meta.failed
        assert bool(page.items) is (case_id == "success")
        assert len(client.calls) == 1
        return

    if case_id == "invalid_config":
        client = ScriptedSearchClient(definition.success_response)
        provider = definition.build_provider(client, False)
        error = await _provider_error(provider, definition.request, context)
        assert error.code is ProviderErrorCode.INVALID_CONFIG
        assert client.calls == []
        return

    if case_id == "cancellation":
        client = ScriptedSearchClient(BLOCK)
        provider = definition.build_provider(client, True)
        cancel_event = asyncio.Event()
        task = asyncio.create_task(
            provider.search(
                definition.request,
                context,
                ExecutionContext.with_timeout(5, cancel_event=cancel_event),
            )
        )
        await asyncio.wait_for(client.entered.wait(), timeout=1)
        cancel_event.set()
        with pytest.raises(ProviderError) as exc_info:
            await asyncio.wait_for(task, timeout=1)
        assert exc_info.value.code is ProviderErrorCode.CANCELLED
        assert client.cancelled.is_set()
        return

    if case_id == "rate_limit":
        client = ScriptedSearchClient(RateLimitError("secret-rate-limit-canary", retry_after=3))
        error = await _provider_error(
            definition.build_provider(client, True), definition.request, context
        )
        assert error.code is ProviderErrorCode.RATE_LIMITED
        assert error.retry_after_seconds == 3
        assert "secret-rate-limit-canary" not in str(error)
        return

    if case_id == "invalid_upstream":
        client = ScriptedSearchClient(definition.invalid_response)
        error = await _provider_error(
            definition.build_provider(client, True), definition.request, context
        )
        assert error.code is ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
        return

    if case_id == "policy_blocked":
        client = ScriptedSearchClient(
            ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id=definition.provider_id)
        )
        error = await _provider_error(
            definition.build_provider(client, True), definition.request, context
        )
        assert error.code is ProviderErrorCode.POLICY_BLOCKED
        return

    if case_id == "probe_close":
        client = ScriptedSearchClient(definition.success_response)
        provider = definition.build_provider(client, True)
        execution = ExecutionContext.with_timeout(5)
        available = await provider.probe(execution)
        await provider.close()
        await provider.close()
        unavailable = await provider.probe(ExecutionContext.with_timeout(5))
        assert (available.provider, available.capability, available.status) == (
            definition.provider_id,
            "search",
            "available",
        )
        assert unavailable.status == "unavailable"
        assert client.calls == []
        assert client.close_count == 1
        return

    secret = "provider-v2-redaction-canary"
    client = ScriptedSearchClient(RuntimeError(secret))
    error = await _provider_error(
        definition.build_provider(client, True), definition.request, context
    )
    assert error.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert secret not in str(error)
    assert secret not in repr(error)


async def _provider_error(
    provider: Any, request: SearchRequest, context: RequestContext
) -> ProviderError:
    with pytest.raises(ProviderError) as exc_info:
        await provider.search(request, context, ExecutionContext.with_timeout(5))
    return exc_info.value


__all__ = [
    "SEARCH_CONFORMANCE_CASES",
    "ScriptedSearchClient",
    "SearchConformanceDefinition",
    "run_search_conformance_case",
]
