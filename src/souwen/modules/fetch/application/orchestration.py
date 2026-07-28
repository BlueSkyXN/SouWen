"""Canonical Fetch batch orchestration through an injected Provider Manager port."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from souwen.platform.provider_spi import (
    ErrorDetail,
    ExecutionContext,
    FetchBatch,
    FetchMeta,
    FetchRequest,
    FetchResult,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
)


BUILTIN_FETCH_ADAPTER_ID = "builtin-fetch"


@dataclass(frozen=True, slots=True)
class _TargetOutcome:
    result: FetchResult
    error: ProviderError | None = None


class FetchProviderManager(Protocol):
    async def execute(
        self,
        adapter_id: str,
        request: FetchTargetRequest,
        request_context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchResult:
        """Execute one target through one selected Fetch adapter."""


class BrowserFetchExecutor(Protocol):
    async def fetch(
        self,
        request: FetchTargetRequest,
        request_context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchResult:
        """Execute the browser fallback mode without selecting another business Provider."""


class FetchModuleService:
    """Run the target builtin Fetch provider for every canonical target."""

    def __init__(
        self,
        manager: FetchProviderManager,
        configured_adapter_id: str = BUILTIN_FETCH_ADAPTER_ID,
        provider_adapter_ids: Mapping[str, str] | None = None,
        browser_executor: BrowserFetchExecutor | None = None,
    ) -> None:
        if not configured_adapter_id.strip():
            raise ValueError("configured_adapter_id must not be blank")
        self._manager = manager
        self._adapter_id = configured_adapter_id
        self._provider_adapter_ids = {
            configured_adapter_id: configured_adapter_id,
            **dict(provider_adapter_ids or {}),
        }
        if any(
            not provider_id.strip() or not adapter_id.strip()
            for provider_id, adapter_id in self._provider_adapter_ids.items()
        ):
            raise ValueError("provider and adapter IDs must not be blank")
        self._browser_executor = browser_executor

    async def fetch(
        self,
        request: FetchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchBatch:
        execution.raise_if_cancelled_or_expired()
        if request.strategy not in {None, "fallback"}:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)
        adapter_id = self._adapter_id
        if request.providers is not None:
            if len(request.providers) != 1 or request.providers[0].kind != "fetch":
                raise ProviderError(ProviderErrorCode.INVALID_REQUEST)
            adapter_id = self._provider_adapter_ids.get(request.providers[0].id, "")
            if not adapter_id:
                raise ProviderError(ProviderErrorCode.INVALID_REQUEST)

        outcomes = await asyncio.gather(
            *(
                self._fetch_target(target, request, context, execution, adapter_id)
                for target in request.targets
            )
        )
        items = [outcome.result for outcome in outcomes]
        execution.raise_if_cancelled_or_expired()
        if not any(item.status == "success" for item in items):
            raise _all_failed_error(outcomes, adapter_id)
        partial = any(
            item.status != "success"
            or item.content_metadata is None
            or item.content_metadata.quality == "low"
            for item in items
        )
        return FetchBatch(items=items, meta=FetchMeta(partial=partial), context=context)

    async def _fetch_target(
        self,
        target: object,
        request: FetchRequest,
        context: RequestContext,
        execution: ExecutionContext,
        adapter_id: str,
    ) -> _TargetOutcome:
        target_request = FetchTargetRequest(
            target=target,
            content=request.content,
            policy=request.policy,
        )
        try:
            builtin_result = await self._manager.execute(
                adapter_id,
                target_request,
                context,
                execution,
            )
            builtin_error = None
        except ProviderError as exc:
            builtin_error = exc
            builtin_result = _failed_result(target_request, context, adapter_id, exc)
        except Exception:
            builtin_error = ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE)
            builtin_result = _failed_result(
                target_request,
                context,
                adapter_id,
                builtin_error,
            )

        if adapter_id != self._adapter_id or not self._should_try_browser(
            target_request, builtin_result
        ):
            return _TargetOutcome(builtin_result, builtin_error)
        try:
            browser_result = await self._browser_executor.fetch(
                target_request,
                context,
                execution,
            )
            browser_error = None
        except ProviderError as exc:
            browser_error = exc
            browser_result = _failed_result(target_request, context, adapter_id, exc)
        except Exception:
            browser_error = ProviderError(ProviderErrorCode.WORKER_UNAVAILABLE)
            browser_result = _failed_result(
                target_request,
                context,
                adapter_id,
                browser_error,
            )
        if builtin_result.status == "success":
            if browser_result.status == "success":
                return _TargetOutcome(
                    browser_result.model_copy(
                        update={
                            "provenance": builtin_result.provenance + browser_result.provenance,
                        }
                    )
                )
            return _TargetOutcome(
                builtin_result.model_copy(
                    update={
                        "provenance": builtin_result.provenance + browser_result.provenance,
                    }
                )
            )
        return _TargetOutcome(
            browser_result.model_copy(
                update={
                    "provenance": builtin_result.provenance + browser_result.provenance,
                }
            ),
            browser_error,
        )

    def _should_try_browser(
        self,
        request: FetchTargetRequest,
        result: FetchResult,
    ) -> bool:
        if self._browser_executor is None:
            return False
        if request.policy is not None and request.policy.respect_robots is True:
            return False
        if result.status == "success":
            return result.content_metadata is not None and result.content_metadata.quality == "low"
        return result.error is not None and result.error.code in {
            "provider_timeout",
            "provider_unavailable",
        }


def _failed_result(
    request: FetchTargetRequest,
    context: RequestContext,
    adapter_id: str,
    error: ProviderError,
) -> FetchResult:
    code = _canonical_error_code(error.code)
    return FetchResult(
        target=request.target,
        final_url=None,
        status="blocked" if error.code is ProviderErrorCode.POLICY_BLOCKED else "failed",
        provenance=(Provenance(provider=adapter_id, outcome="failed"),),
        error=ErrorDetail(
            code=code,
            message=_safe_error_message(code),
            retryable=error.retryable,
            request_id=context.request_id,
            provider=adapter_id,
        ),
    )


def _canonical_error_code(code: ProviderErrorCode) -> str:
    return {
        ProviderErrorCode.INVALID_REQUEST: "invalid_request",
        ProviderErrorCode.CANCELLED: "provider_timeout",
        ProviderErrorCode.DEADLINE_EXCEEDED: "provider_timeout",
        ProviderErrorCode.RATE_LIMITED: "rate_limited",
        ProviderErrorCode.POLICY_BLOCKED: "policy_blocked",
        ProviderErrorCode.PAYLOAD_TOO_LARGE: "payload_too_large",
        ProviderErrorCode.UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
        ProviderErrorCode.WORKER_UNAVAILABLE: "worker_unavailable",
        ProviderErrorCode.WORKER_NOT_READY: "worker_not_ready",
        ProviderErrorCode.WORKER_OVERLOADED: "worker_overloaded",
        ProviderErrorCode.WORKER_TIMEOUT: "worker_timeout",
        ProviderErrorCode.WORKER_PROTOCOL_MISMATCH: "worker_protocol_mismatch",
    }.get(code, "provider_unavailable")


def _safe_error_message(code: str) -> str:
    return {
        "invalid_request": "Fetch request is invalid",
        "provider_timeout": "Fetch provider timed out",
        "rate_limited": "Fetch provider was rate limited",
        "policy_blocked": "Fetch target was blocked by policy",
        "payload_too_large": "Fetch response exceeded the size limit",
        "unsupported_media_type": "Fetch response media type is unsupported",
        "worker_unavailable": "Browser Worker is unavailable",
        "worker_not_ready": "Browser Worker is not ready",
        "worker_overloaded": "Browser Worker is overloaded",
        "worker_timeout": "Browser Worker timed out",
        "worker_protocol_mismatch": "Browser Worker protocol does not match",
        "provider_unavailable": "Fetch provider is unavailable",
    }[code]


def _all_failed_error(outcomes: list[_TargetOutcome], adapter_id: str) -> ProviderError:
    errors = [outcome.error for outcome in outcomes if outcome.error is not None]
    codes = {error.code for error in errors}
    provider_code = next(iter(codes)) if len(codes) == 1 else ProviderErrorCode.PROVIDER_UNAVAILABLE
    retry_after = None
    if provider_code is ProviderErrorCode.RATE_LIMITED:
        retry_values = [
            error.retry_after_seconds for error in errors if error.retry_after_seconds is not None
        ]
        retry_after = max(retry_values) if retry_values else None
    return ProviderError(
        provider_code,
        provider_id=adapter_id,
        retry_after_seconds=retry_after,
    )


__all__ = [
    "BUILTIN_FETCH_ADAPTER_ID",
    "BrowserFetchExecutor",
    "FetchModuleService",
    "FetchProviderManager",
]
