"""Canonical Fetch batch orchestration through an injected Provider Manager port."""

from __future__ import annotations

import asyncio
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


class FetchProviderManager(Protocol):
    async def execute(
        self,
        adapter_id: str,
        request: FetchTargetRequest,
        request_context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchResult:
        """Execute one target through one selected Fetch adapter."""


class FetchModuleService:
    """Run the RC2 builtin Fetch provider for every canonical target."""

    def __init__(
        self,
        manager: FetchProviderManager,
        configured_adapter_id: str = BUILTIN_FETCH_ADAPTER_ID,
    ) -> None:
        if not configured_adapter_id.strip():
            raise ValueError("configured_adapter_id must not be blank")
        self._manager = manager
        self._adapter_id = configured_adapter_id

    async def fetch(
        self,
        request: FetchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchBatch:
        execution.raise_if_cancelled_or_expired()
        if request.strategy not in {None, "fallback"}:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)
        if request.providers is not None and (
            len(request.providers) != 1
            or request.providers[0].kind != "fetch"
            or request.providers[0].id != self._adapter_id
        ):
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)

        items = await asyncio.gather(
            *(self._fetch_target(target, request, context, execution) for target in request.targets)
        )
        execution.raise_if_cancelled_or_expired()
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
    ) -> FetchResult:
        target_request = FetchTargetRequest(
            target=target,
            content=request.content,
            policy=request.policy,
        )
        try:
            return await self._manager.execute(
                self._adapter_id,
                target_request,
                context,
                execution,
            )
        except ProviderError as exc:
            return _failed_result(target_request, context, self._adapter_id, exc)
        except Exception:
            return _failed_result(
                target_request,
                context,
                self._adapter_id,
                ProviderError(ProviderErrorCode.PROVIDER_UNAVAILABLE),
            )


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
    }.get(code, "provider_unavailable")


def _safe_error_message(code: str) -> str:
    return {
        "invalid_request": "Fetch request is invalid",
        "provider_timeout": "Fetch provider timed out",
        "rate_limited": "Fetch provider was rate limited",
        "policy_blocked": "Fetch target was blocked by policy",
        "payload_too_large": "Fetch response exceeded the size limit",
        "unsupported_media_type": "Fetch response media type is unsupported",
        "provider_unavailable": "Fetch provider is unavailable",
    }[code]


__all__ = ["BUILTIN_FETCH_ADAPTER_ID", "FetchModuleService", "FetchProviderManager"]
