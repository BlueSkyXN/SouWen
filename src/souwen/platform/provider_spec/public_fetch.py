"""Strict projection helpers for existing Fetch clients using validated public targets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from souwen.common_runtime.security import validate_fetch_url
from souwen.platform.provider_spi import (
    ContentMetadata,
    FetchResult,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    Provenance,
)


def public_fetch_target(request: FetchTargetRequest, provider_id: str) -> str:
    if request.policy is not None and request.policy.respect_robots:
        raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=provider_id)
    target = str(request.target)
    if not validate_fetch_url(target)[0]:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id=provider_id)
    return target


def project_public_fetch_receipt(
    receipt: Any,
    request: FetchTargetRequest,
    provider_id: str,
) -> FetchResult:
    if getattr(receipt, "source", None) != provider_id:
        raise ValueError("unexpected existing source")
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
        raise ValueError("invalid existing receipt content")
    max_code_points = request.content.max_code_points if request.content else None
    truncated = max_code_points is not None and len(content) > max_code_points
    if max_code_points is not None:
        content = content[:max_code_points]
    final_url = getattr(receipt, "final_url", None)
    if not isinstance(final_url, str) or not validate_fetch_url(final_url)[0]:
        raise ValueError("invalid existing final URL")
    media_type = {
        "text": "text/plain",
        "markdown": "text/markdown",
        "html": "text/html",
    }.get(getattr(receipt, "content_format", None))
    if media_type is None:
        raise ValueError("invalid existing content format")
    title = getattr(receipt, "title", None)
    if title is not None and not isinstance(title, str):
        raise ValueError("invalid existing title")
    retrieved_at = datetime.now(timezone.utc)
    return FetchResult(
        target=request.target,
        final_url=final_url,
        status="success",
        title=title or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type=media_type,
            retrieved_at=retrieved_at,
            truncated=truncated,
            content_length=len(content.encode()),
            quality="low" if len(content.strip()) <= 63 else "high",
        ),
        provenance=(
            Provenance(
                provider=provider_id,
                attempt=1,
                outcome="success",
                retrieved_at=retrieved_at,
            ),
        ),
    )


__all__ = ["project_public_fetch_receipt", "public_fetch_target"]
