from __future__ import annotations
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


class WaybackClientProtocol(Protocol):
    async def fetch(self, url: str, timeout: float = 30.0) -> Any: ...
    async def close(self) -> None: ...


class WaybackFetchProvider(LegacyFetchProvider):
    def __init__(self, client: WaybackClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: FetchTargetRequest) -> Any:
    return await client.fetch(_target(request), timeout=30.0)


def _project(receipt: Any, request: FetchTargetRequest, context: RequestContext) -> FetchResult:
    del context
    if getattr(receipt, "source", None) != "wayback":
        raise ValueError("invalid Wayback receipt")
    if getattr(receipt, "error", None):
        raw = getattr(receipt, "raw", None)
        code = (
            ProviderErrorCode.POLICY_BLOCKED
            if isinstance(raw, dict) and raw.get("blocked_by_ssrf")
            else ProviderErrorCode.PROVIDER_UNAVAILABLE
        )
        raise ProviderError(code, provider_id="wayback")
    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("invalid Wayback content")
    final = _url(str(getattr(receipt, "final_url", None) or request.target))
    if final != _url(str(request.target)) or not validate_fetch_url(final)[0]:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id="wayback")
    title = getattr(receipt, "title", None)
    if title is not None and not isinstance(title, str):
        raise ValueError("invalid Wayback title")
    now = datetime.now(timezone.utc)
    return FetchResult(
        target=request.target,
        final_url=final,
        status="success",
        title=title or None,
        content=content,
        content_metadata=ContentMetadata(
            media_type="text/html",
            retrieved_at=now,
            truncated=False,
            content_length=len(content.encode()),
            quality="low" if len(content.strip()) <= 63 else "high",
        ),
        provenance=(
            Provenance(provider="wayback", attempt=1, outcome="success", retrieved_at=now),
        ),
    )


def _url(value: str) -> str:
    p = urlsplit(value)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("invalid target URL")
    return value


def _target(request: FetchTargetRequest) -> str:
    try:
        target = _url(str(request.target))
    except ValueError as exc:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id="wayback") from exc
    if not validate_fetch_url(target)[0]:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id="wayback")
    return target


_SPEC = LegacyFetchSpec("wayback", _invoke, _project)
