"""Canonical target error translation with no raw provider detail."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time

from fastapi.responses import JSONResponse

from souwen.platform.provider_spi import (
    CanonicalErrorCode,
    ErrorDetail,
    ErrorResponse,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
)


_SAFE_MESSAGES: dict[CanonicalErrorCode, str] = {
    "invalid_request": "Request is invalid",
    "unauthenticated": "Authentication is required",
    "forbidden": "Permission is denied",
    "not_found": "Resource was not found",
    "conflict": "Request conflicts with current state",
    "api_major_mismatch": "Client API major does not match",
    "rate_limited": "Request rate limit was reached",
    "payload_too_large": "Response exceeded the size limit",
    "unsupported_media_type": "Response media type is unsupported",
    "worker_unavailable": "Browser Worker is unavailable",
    "worker_not_ready": "Browser Worker is not ready",
    "worker_overloaded": "Browser Worker is overloaded",
    "worker_timeout": "Browser Worker timed out",
    "worker_protocol_mismatch": "Browser Worker protocol does not match",
    "provider_timeout": "Provider timed out",
    "provider_unavailable": "Provider is unavailable",
    "policy_blocked": "Operation was blocked by policy",
    "internal_error": "Service encountered an internal error",
}


@dataclass(frozen=True, slots=True)
class TargetDeliveryError(Exception):
    code: CanonicalErrorCode
    status_code: int
    retryable: bool = False
    provider: str | None = None
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")
        Exception.__init__(self, self.code)


def from_provider_error(error: ProviderError) -> TargetDeliveryError:
    mapping: dict[ProviderErrorCode, tuple[CanonicalErrorCode, int]] = {
        ProviderErrorCode.INVALID_REQUEST: ("invalid_request", 400),
        ProviderErrorCode.INVALID_CONFIG: ("provider_unavailable", 502),
        ProviderErrorCode.CANCELLED: ("provider_timeout", 504),
        ProviderErrorCode.DEADLINE_EXCEEDED: ("provider_timeout", 504),
        ProviderErrorCode.RATE_LIMITED: ("rate_limited", 429),
        ProviderErrorCode.PROVIDER_UNAVAILABLE: ("provider_unavailable", 502),
        ProviderErrorCode.INVALID_UPSTREAM_RESPONSE: ("provider_unavailable", 502),
        ProviderErrorCode.POLICY_BLOCKED: ("policy_blocked", 403),
        ProviderErrorCode.PAYLOAD_TOO_LARGE: ("payload_too_large", 413),
        ProviderErrorCode.UNSUPPORTED_MEDIA_TYPE: ("unsupported_media_type", 415),
        ProviderErrorCode.WORKER_UNAVAILABLE: ("worker_unavailable", 502),
        ProviderErrorCode.WORKER_NOT_READY: ("worker_not_ready", 503),
        ProviderErrorCode.WORKER_OVERLOADED: ("worker_overloaded", 503),
        ProviderErrorCode.WORKER_TIMEOUT: ("worker_timeout", 504),
        ProviderErrorCode.WORKER_PROTOCOL_MISMATCH: ("worker_protocol_mismatch", 409),
    }
    code, status_code = mapping[error.code]
    return TargetDeliveryError(
        code,
        status_code,
        retryable=error.retryable,
        provider=error.provider_id,
        retry_after_seconds=error.retry_after_seconds,
    )


def error_response(
    error: TargetDeliveryError,
    request_id: str,
    *,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    headers = dict(extra_headers or {})
    if error.status_code == 429:
        retry_after = max(1, math.ceil(error.retry_after_seconds or 1))
        headers.setdefault("Retry-After", str(retry_after))
        headers.setdefault("X-RateLimit-Limit", "unknown")
        headers.setdefault("X-RateLimit-Remaining", "0")
        headers.setdefault("X-RateLimit-Reset", str(math.ceil(time.time() + retry_after)))
    elif error.retry_after_seconds is not None:
        headers["Retry-After"] = str(max(1, math.ceil(error.retry_after_seconds)))
    context = RequestContext(request_id=request_id)
    payload = ErrorResponse(
        error=ErrorDetail(
            code=error.code,
            message=_SAFE_MESSAGES[error.code],
            retryable=error.retryable,
            request_id=request_id,
            provider=error.provider,
        ),
        context=context,
    )
    return JSONResponse(
        status_code=error.status_code,
        content=payload.model_dump(mode="json"),
        headers=headers or None,
    )


def from_http_status(status_code: int) -> TargetDeliveryError:
    mapping: dict[int, CanonicalErrorCode] = {
        400: "invalid_request",
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        405: "invalid_request",
        409: "conflict",
        413: "payload_too_large",
        415: "unsupported_media_type",
        429: "rate_limited",
        502: "provider_unavailable",
        503: "provider_unavailable",
        504: "provider_timeout",
    }
    code = mapping.get(status_code, "internal_error")
    return TargetDeliveryError(
        code,
        400 if status_code == 405 else status_code if code != "internal_error" else 500,
        retryable=status_code in {429, 502, 503, 504},
    )


__all__ = [
    "TargetDeliveryError",
    "error_response",
    "from_http_status",
    "from_provider_error",
]
