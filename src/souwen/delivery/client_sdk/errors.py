"""Stable public errors for the generated target REST SDK."""

from __future__ import annotations

from ._generated_models import ErrorResponse


class SouWenSDKError(Exception):
    """Base class for SDK-owned failures."""


class ApiMajorMismatchError(SouWenSDKError):
    """The server did not prove support for the SDK wire major."""

    def __init__(self, expected: int, received: str | None) -> None:
        self.expected = expected
        self.received = received
        super().__init__(f"SouWen API major mismatch: expected {expected}, received {received!r}")


class ContractViolationError(SouWenSDKError):
    """The response violated the frozen target contract."""


class SouWenTransportError(SouWenSDKError):
    """The HTTP exchange failed before a canonical response was available."""


class SouWenAPIError(SouWenSDKError):
    """A canonical non-success response from the target API."""

    def __init__(
        self,
        status_code: int,
        payload: ErrorResponse,
        *,
        retry_after: str | None = None,
        rate_limit: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.request_id = payload.context.request_id
        self.retry_after = retry_after
        self.rate_limit = dict(rate_limit or {})
        detail = payload.error
        super().__init__(
            f"SouWen API error {status_code} {detail.code}: {detail.message} "
            f"(request_id={self.request_id})"
        )


__all__ = [
    "ApiMajorMismatchError",
    "ContractViolationError",
    "SouWenAPIError",
    "SouWenSDKError",
    "SouWenTransportError",
]
