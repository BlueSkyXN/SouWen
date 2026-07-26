"""Canonical ScraperAPI Fetch bridge over the SSRF-safe legacy client."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from souwen.common_runtime.security import validate_fetch_url
from souwen.platform.provider_spi import (
    ContentMetadata,
    FetchResult,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
)
from souwen.platform.provider_spec import LegacyFetchProvider, LegacyFetchSpec

from .spec import SCRAPERAPI_FETCH_PROFILE


class ScraperAPIClientProtocol(Protocol):
    async def fetch(self, url: str, timeout: float = 30.0) -> Any: ...
    async def close(self) -> None: ...


class ScraperAPIFetchProvider(LegacyFetchProvider):
    capability = "fetch"

    def __init__(self, client: ScraperAPIClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _FETCH_SPEC, enabled=enabled)


async def _invoke(client: Any, request: FetchTargetRequest) -> Any:
    return await client.fetch(_target(request), timeout=30.0)


def _project(receipt: Any, request: FetchTargetRequest, context: RequestContext) -> FetchResult:
    del context
    return _result(receipt, request, SCRAPERAPI_FETCH_PROFILE.provider_id)


def _target(request: FetchTargetRequest) -> str:
    target = str(request.target)
    if not validate_fetch_url(target)[0]:
        raise ProviderError(
            ProviderErrorCode.POLICY_BLOCKED, provider_id=SCRAPERAPI_FETCH_PROFILE.provider_id
        )
    return target


def _result(receipt: Any, request: FetchTargetRequest, provider_id: str) -> FetchResult:
    if getattr(receipt, "source", None) != provider_id:
        raise ValueError("unexpected legacy source")
    if getattr(receipt, "error", None):
        raw = getattr(receipt, "raw", None)
        code = (
            ProviderErrorCode.POLICY_BLOCKED
            if isinstance(raw, dict) and raw.get("blocked_by_ssrf")
            else ProviderErrorCode.PROVIDER_UNAVAILABLE
        )
        raise ProviderError(code, provider_id=provider_id)
    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("invalid legacy receipt content")
    final_url = getattr(receipt, "final_url", None)
    if not isinstance(final_url, str) or not validate_fetch_url(final_url)[0]:
        raise ValueError("invalid legacy final URL")
    content_format = getattr(receipt, "content_format", None)
    media_type = {"text": "text/plain", "markdown": "text/markdown"}.get(content_format)
    if media_type is None:
        raise ValueError("invalid legacy content format")
    retrieved_at = datetime.now(timezone.utc)
    title = getattr(receipt, "title", None)
    if title is not None and not isinstance(title, str):
        raise ValueError("invalid legacy title")
    return FetchResult(
        target=request.target,
        final_url=final_url,
        status="success",
        title=title or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type=media_type,
            retrieved_at=retrieved_at,
            truncated=False,
            content_length=len(content.encode()),
            quality="low" if len(content.strip()) <= 63 else "high",
        ),
        provenance=(
            Provenance(
                provider=provider_id, attempt=1, outcome="success", retrieved_at=retrieved_at
            ),
        ),
    )


_FETCH_SPEC = LegacyFetchSpec(SCRAPERAPI_FETCH_PROFILE.provider_id, _invoke, _project)

__all__ = ["ScraperAPIClientProtocol", "ScraperAPIFetchProvider"]
