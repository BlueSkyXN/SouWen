"""Provider v2 bridges for xcrawl Search and Fetch."""

from __future__ import annotations
from collections.abc import Sequence
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
from souwen.common_runtime.security import validate_fetch_url
from souwen.platform.provider_spi import (
    ContentMetadata,
    FetchResult,
    FetchTargetRequest,
    PageInfo,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)
from souwen.platform.provider_spec import (
    LegacyFetchProvider,
    LegacyFetchSpec,
    LegacySearchProvider,
    LegacySearchSpec,
)

_PROVIDER_ID = "xcrawl"


class XCrawlClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...
    async def scrape(self, url: str, timeout: float = 30.0, **kwargs: Any) -> Any: ...
    async def close(self) -> None: ...


class XCrawlSearchProvider(LegacySearchProvider):
    def __init__(self, client: XCrawlClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SEARCH_SPEC, enabled=enabled)


class XCrawlFetchProvider(LegacyFetchProvider):
    def __init__(self, client: XCrawlClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _FETCH_SPEC, enabled=enabled)


async def _search(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _project_search(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != _PROVIDER_ID
        or getattr(response, "page", None) != 1
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid search response")
    items = []
    for rank, item in enumerate(results, 1):
        if (
            getattr(item, "source", None) != _PROVIDER_ID
            or not isinstance(getattr(item, "title", None), str)
            or not item.title.strip()
        ):
            raise ValueError("invalid search item")
        url = _url(getattr(item, "url", None))
        key = sha256(url.encode()).hexdigest()
        items.append(
            SearchItem(
                id=f"{_PROVIDER_ID}:{key}",
                title=item.title.strip(),
                url=url,
                snippet=_text(getattr(item, "snippet", None)),
                rank=rank,
                provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
                attributes=SearchAttributes(
                    identifiers=(SearchIdentifier(scheme=_PROVIDER_ID, value=key),)
                ),
            )
        )
    return SearchPage(
        items=tuple(items),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


async def _fetch(client: Any, request: FetchTargetRequest) -> Any:
    target = _target(request)
    return await client.scrape(target, timeout=30.0, formats=None, mode="sync")


def _project_fetch(
    receipt: Any, request: FetchTargetRequest, context: RequestContext
) -> FetchResult:
    del context
    receipt = _one(receipt, request)
    if getattr(receipt, "source", None) != _PROVIDER_ID:
        raise ValueError("invalid fetch receipt")
    if getattr(receipt, "error", None):
        raw = getattr(receipt, "raw", None)
        code = (
            ProviderErrorCode.POLICY_BLOCKED
            if isinstance(raw, dict) and raw.get("blocked_by_ssrf")
            else ProviderErrorCode.PROVIDER_UNAVAILABLE
        )
        raise ProviderError(code, provider_id=_PROVIDER_ID)
    content = getattr(receipt, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("invalid fetch content")
    final = _url(getattr(receipt, "final_url", None) or str(request.target))
    if not validate_fetch_url(final)[0]:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id=_PROVIDER_ID)
    now = datetime.now(timezone.utc)
    return FetchResult(
        target=request.target,
        final_url=final,
        status="success",
        title=_text(getattr(receipt, "title", None)),
        content=content,
        content_metadata=ContentMetadata(
            media_type="text/plain",
            retrieved_at=now,
            truncated=False,
            content_length=len(content.encode()),
            quality="low" if len(content.strip()) <= 63 else "high",
        ),
        provenance=(
            Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success", retrieved_at=now),
        ),
    )


def _one(receipt: Any, request: FetchTargetRequest) -> Any:
    results = getattr(receipt, "results", None)
    if results is None:
        return receipt
    if (
        not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) != 1
        or str(getattr(results[0], "url", request.target)) != str(request.target)
    ):
        raise ValueError("invalid batch fetch receipt")
    return results[0]


def _target(request: FetchTargetRequest) -> str:
    try:
        target = _url(str(request.target))
    except ValueError as exc:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id=_PROVIDER_ID) from exc
    if not validate_fetch_url(target)[0]:
        raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id=_PROVIDER_ID)
    return target


def _url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid URL")
    p = urlsplit(value.strip())
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("invalid URL")
    return urlunsplit((p.scheme.lower(), p.netloc, p.path or "/", p.query, ""))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid text")
    return value.strip() or None


_SEARCH_SPEC = LegacySearchSpec(_PROVIDER_ID, "web", _search, _project_search)
_FETCH_SPEC = LegacyFetchSpec(_PROVIDER_ID, _fetch, _project_fetch)
