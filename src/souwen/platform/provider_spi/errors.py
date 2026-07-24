"""Safe provider-side error taxonomy for target SPI implementations."""

from __future__ import annotations

from enum import Enum


class ProviderErrorCode(str, Enum):
    """The only provider error classes allowed across the Core/SPI boundary."""

    INVALID_REQUEST = "invalid_request"
    INVALID_CONFIG = "invalid_config"
    CANCELLED = "cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_UPSTREAM_RESPONSE = "invalid_upstream_response"
    POLICY_BLOCKED = "policy_blocked"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    WORKER_UNAVAILABLE = "worker_unavailable"
    WORKER_NOT_READY = "worker_not_ready"
    WORKER_OVERLOADED = "worker_overloaded"
    WORKER_TIMEOUT = "worker_timeout"
    WORKER_PROTOCOL_MISMATCH = "worker_protocol_mismatch"


_SAFE_MESSAGES: dict[ProviderErrorCode, str] = {
    ProviderErrorCode.INVALID_REQUEST: "Provider request is invalid",
    ProviderErrorCode.INVALID_CONFIG: "Provider configuration is invalid",
    ProviderErrorCode.CANCELLED: "Provider execution was cancelled",
    ProviderErrorCode.DEADLINE_EXCEEDED: "Provider execution exceeded its deadline",
    ProviderErrorCode.RATE_LIMITED: "Provider rate limit was reached",
    ProviderErrorCode.PROVIDER_UNAVAILABLE: "Provider is unavailable",
    ProviderErrorCode.INVALID_UPSTREAM_RESPONSE: "Provider returned an invalid response",
    ProviderErrorCode.POLICY_BLOCKED: "Provider operation was blocked by policy",
    ProviderErrorCode.PAYLOAD_TOO_LARGE: "Provider response exceeded the size limit",
    ProviderErrorCode.UNSUPPORTED_MEDIA_TYPE: "Provider response media type is unsupported",
    ProviderErrorCode.WORKER_UNAVAILABLE: "Browser Worker is unavailable",
    ProviderErrorCode.WORKER_NOT_READY: "Browser Worker is not ready",
    ProviderErrorCode.WORKER_OVERLOADED: "Browser Worker is overloaded",
    ProviderErrorCode.WORKER_TIMEOUT: "Browser Worker timed out",
    ProviderErrorCode.WORKER_PROTOCOL_MISMATCH: "Browser Worker protocol does not match",
}


class ProviderError(Exception):
    """A typed provider failure that deliberately accepts no raw upstream detail."""

    def __init__(
        self,
        code: ProviderErrorCode,
        *,
        provider_id: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")
        self.code = code
        self.provider_id = provider_id
        self.retry_after_seconds = retry_after_seconds
        self.retryable = code in {
            ProviderErrorCode.DEADLINE_EXCEEDED,
            ProviderErrorCode.RATE_LIMITED,
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            ProviderErrorCode.WORKER_UNAVAILABLE,
            ProviderErrorCode.WORKER_NOT_READY,
            ProviderErrorCode.WORKER_OVERLOADED,
            ProviderErrorCode.WORKER_TIMEOUT,
        }
        super().__init__(_SAFE_MESSAGES[code])


__all__ = ["ProviderError", "ProviderErrorCode"]
