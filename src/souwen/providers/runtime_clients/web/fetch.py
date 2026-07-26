"""Provider-local SSRF helpers for direct fetch clients.

This module deliberately does not select, dispatch, or aggregate providers.
Each provider owns its own transport and lifecycle; shared URL-safety helpers
remain here until they receive a narrower common-runtime home.
"""

from __future__ import annotations

from souwen.common_runtime.security import (
    ResolvedFetchTarget as ResolvedFetchTarget,
    resolve_fetch_target as resolve_fetch_target,
    validate_fetch_url,
)
from souwen.providers.runtime_clients.models import FetchResult


def ssrf_blocked_fetch_result(
    url: str,
    provider: str,
    *,
    raw_provider: str | None = None,
) -> FetchResult | None:
    """Return a blocked result when a provider-level URL safety check fails."""
    ok, reason = validate_fetch_url(url)
    if ok:
        return None
    raw_name = raw_provider or provider
    return FetchResult(
        url=url,
        final_url=url,
        source=provider,
        error=f"SSRF 校验失败: {reason}",
        raw={"provider": raw_name, "blocked_by_ssrf": True},
    )


def raise_if_fetch_url_blocked(url: str) -> None:
    """Raise when a direct URL API cannot represent blocked results."""
    ok, reason = validate_fetch_url(url)
    if not ok:
        raise ValueError(f"SSRF 校验失败: {reason}")


def split_fetch_urls_by_ssrf(
    urls: list[str],
    provider: str,
    *,
    raw_provider: str | None = None,
) -> tuple[list[str], list[FetchResult]]:
    """Split a batch into safe URLs and blocked-result placeholders."""
    safe_urls: list[str] = []
    blocked_results: list[FetchResult] = []
    for url in urls:
        blocked = ssrf_blocked_fetch_result(url, provider, raw_provider=raw_provider)
        if blocked is None:
            safe_urls.append(url)
        else:
            blocked_results.append(blocked)
    return safe_urls, blocked_results
