"""Canonical builtin Fetch adapter over the existing SSRF-safe fetch client."""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from souwen.common_runtime.errors import SouWenError
from souwen.common_runtime.transport.errors import RateLimitError, SourceUnavailableError
from souwen.platform.provider_spi import (
    ContentMetadata,
    ExecutionContext,
    FetchResult,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    ProviderProbe,
    Provenance,
    RequestContext,
)


_PROVIDER_ID = "builtin-fetch"
_DEFAULT_MAX_CODE_POINTS = 200_000


class LegacyBuiltinFetchClientProtocol(Protocol):
    async def fetch(
        self,
        url: str,
        timeout: float = 30.0,
        start_index: int = 0,
        max_length: int | None = None,
        respect_robots_txt: bool | None = None,
        selector: str | None = None,
        enforce_target_contract: bool = False,
    ) -> Any:
        """Return a legacy FetchResult produced by the safe redirect pipeline."""


class BuiltinFetchProvider:
    """Fetch one target with mandatory target media, size, and URL policy."""

    capability = "fetch"

    def __init__(
        self,
        client: LegacyBuiltinFetchClientProtocol,
        *,
        enabled: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._closed = False

    async def fetch(
        self,
        request: FetchTargetRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchResult:
        execution.raise_if_cancelled_or_expired()
        if self._closed or not self._enabled:
            raise ProviderError(ProviderErrorCode.INVALID_CONFIG, provider_id=_PROVIDER_ID)
        max_code_points = (
            request.content.max_code_points
            if request.content is not None and request.content.max_code_points is not None
            else _DEFAULT_MAX_CODE_POINTS
        )
        try:
            receipt = await asyncio.wait_for(
                self._client.fetch(
                    str(request.target),
                    timeout=min(30.0, execution.remaining_seconds),
                    max_length=max_code_points,
                    respect_robots_txt=(
                        request.policy.respect_robots if request.policy is not None else None
                    ),
                    enforce_target_contract=True,
                ),
                timeout=execution.remaining_seconds,
            )
            execution.raise_if_cancelled_or_expired()
            return _canonical_result(
                receipt,
                request=request,
                context=context,
                retrieved_at=self._clock(),
            )
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except (asyncio.TimeoutError, TimeoutError):
            raise ProviderError(
                ProviderErrorCode.DEADLINE_EXCEEDED,
                provider_id=_PROVIDER_ID,
            ) from None
        except RateLimitError as exc:
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id=_PROVIDER_ID,
                retry_after_seconds=getattr(exc, "retry_after", None),
            ) from None
        except SourceUnavailableError:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_id=_PROVIDER_ID,
            ) from None
        except (AttributeError, TypeError, ValueError):
            raise ProviderError(
                ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
                provider_id=_PROVIDER_ID,
            ) from None
        except SouWenError:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_id=_PROVIDER_ID,
            ) from None
        except Exception:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_id=_PROVIDER_ID,
            ) from None

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        execution.raise_if_cancelled_or_expired()
        return ProviderProbe(
            provider=_PROVIDER_ID,
            capability="fetch",
            status="unavailable" if self._closed or not self._enabled else "available",
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        closer = getattr(self._client, "close", None) or getattr(self._client, "aclose", None)
        if closer is None:
            return
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            self._closed = False
            raise


def _canonical_result(
    receipt: Any,
    *,
    request: FetchTargetRequest,
    context: RequestContext,
    retrieved_at: datetime,
) -> FetchResult:
    del context
    raw = getattr(receipt, "raw", None)
    if not isinstance(raw, dict):
        raise ValueError("missing target receipt metadata")
    error_code = raw.get("target_error_code")
    if getattr(receipt, "error", None):
        code = {
            "policy_blocked": ProviderErrorCode.POLICY_BLOCKED,
            "response_too_large": ProviderErrorCode.PAYLOAD_TOO_LARGE,
            "unsupported_media_type": ProviderErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "empty_content": ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
        }.get(error_code, ProviderErrorCode.PROVIDER_UNAVAILABLE)
        raise ProviderError(code, provider_id=_PROVIDER_ID)

    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ProviderError(
            ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
            provider_id=_PROVIDER_ID,
        )
    media_type = raw.get("media_type")
    if not isinstance(media_type, str) or not media_type:
        raise ValueError("missing media type")
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at must be timezone-aware")
    final_url = getattr(receipt, "final_url", None)
    return FetchResult(
        target=request.target,
        final_url=final_url,
        status="success",
        title=getattr(receipt, "title", None) or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type=media_type,
            charset=raw.get("charset") if isinstance(raw.get("charset"), str) else None,
            retrieved_at=retrieved_at,
            truncated=bool(getattr(receipt, "content_truncated", False)),
            content_length=(
                raw.get("content_length_bytes")
                if isinstance(raw.get("content_length_bytes"), int)
                else None
            ),
            quality="low" if len(content.strip()) <= 63 else "high",
        ),
        provenance=(
            Provenance(
                provider=_PROVIDER_ID,
                attempt=1,
                outcome="success",
                retrieved_at=retrieved_at,
            ),
        ),
    )


__all__ = ["BuiltinFetchProvider", "LegacyBuiltinFetchClientProtocol"]
