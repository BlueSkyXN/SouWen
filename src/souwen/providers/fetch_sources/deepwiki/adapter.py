"""Canonical DeepWiki Fetch bridge with a repository-only target policy."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlsplit

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

from .spec import DEEPWIKI_FETCH_PROFILE

_REPOSITORY_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


class DeepWikiClientProtocol(Protocol):
    async def fetch(
        self,
        url_or_shorthand: str,
        max_depth: int = 1,
        mode: str = "aggregate",
        timeout: float = 60.0,
    ) -> Any: ...
    async def close(self) -> None: ...


class DeepWikiFetchProvider(LegacyFetchProvider):
    capability = "fetch"

    def __init__(self, client: DeepWikiClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _FETCH_SPEC, enabled=enabled)


async def _invoke(client: Any, request: FetchTargetRequest) -> Any:
    return await client.fetch(_target(request), max_depth=0, mode="aggregate", timeout=30.0)


def _project(receipt: Any, request: FetchTargetRequest, context: RequestContext) -> FetchResult:
    del context
    provider_id = DEEPWIKI_FETCH_PROFILE.provider_id
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
    if not isinstance(final_url, str) or not _is_safe_deepwiki_final_url(final_url):
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


def _target(request: FetchTargetRequest) -> str:
    target = str(request.target)
    parsed = urlsplit(target)
    shorthand = _deepwiki_shorthand(target)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
        or shorthand is None
        or not validate_fetch_url(target)[0]
    ):
        raise ProviderError(
            ProviderErrorCode.POLICY_BLOCKED, provider_id=DEEPWIKI_FETCH_PROFILE.provider_id
        )
    return shorthand


def _deepwiki_shorthand(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.hostname not in {"deepwiki.com", "github.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or any(_REPOSITORY_PART.fullmatch(part) is None for part in parts):
        return None
    return "/".join(parts)


def _is_safe_deepwiki_final_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "deepwiki.com"
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
        and not parsed.query
        and not parsed.fragment
        and _deepwiki_shorthand(url) is not None
        and validate_fetch_url(url)[0]
    )


_FETCH_SPEC = LegacyFetchSpec(DEEPWIKI_FETCH_PROFILE.provider_id, _invoke, _project)

__all__ = ["DeepWikiClientProtocol", "DeepWikiFetchProvider"]
