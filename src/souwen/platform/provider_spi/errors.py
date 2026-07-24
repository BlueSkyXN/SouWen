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


_SAFE_MESSAGES: dict[ProviderErrorCode, str] = {
    ProviderErrorCode.INVALID_REQUEST: "Provider request is invalid",
    ProviderErrorCode.INVALID_CONFIG: "Provider configuration is invalid",
    ProviderErrorCode.CANCELLED: "Provider execution was cancelled",
    ProviderErrorCode.DEADLINE_EXCEEDED: "Provider execution exceeded its deadline",
    ProviderErrorCode.RATE_LIMITED: "Provider rate limit was reached",
    ProviderErrorCode.PROVIDER_UNAVAILABLE: "Provider is unavailable",
    ProviderErrorCode.INVALID_UPSTREAM_RESPONSE: "Provider returned an invalid response",
    ProviderErrorCode.POLICY_BLOCKED: "Provider operation was blocked by policy",
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
        }
        super().__init__(_SAFE_MESSAGES[code])


__all__ = ["ProviderError", "ProviderErrorCode"]
