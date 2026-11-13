"""URL reader with in-process caching and ``max_chars``/``start`` pagination.

SPEC 2.3/4.5: one ``fetch(url, max_chars, start)`` call returns a metadata
line plus the requested slice of the page body; the full body of a URL is
cached in-process for ten minutes so continuation reads do not refetch.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchBatch,
    FetchRequest,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
)

DEFAULT_MAX_CHARS = 20_000
DEFAULT_CACHE_TTL_SECONDS = 600.0
DEFAULT_CACHE_MAX_ENTRIES = 128


class FetchModuleLike(Protocol):
    async def fetch(
        self,
        request: FetchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchBatch: ...


@dataclass(frozen=True, slots=True)
class FetchPage:
    """One bounded slice of a fetched page, flat for every entry point."""

    title: str | None
    url: str
    content: str
    total_chars: int
    start: int
    next_start: int | None
    egress: str
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    page_source: FetchPageSource
    expires_at: float


@dataclass(frozen=True, slots=True)
class FetchPageSource:
    """Full-body fetch outcome kept in the cache between paginated reads."""

    title: str | None
    final_url: str
    content: str
    providers: tuple[str, ...]


class FetchReaderService:
    """Cache full pages, hand out bounded slices, keep failures actionable."""

    def __init__(
        self,
        module: FetchModuleLike,
        *,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        clock=time.monotonic,
    ) -> None:
        self._module = module
        self._ttl = cache_ttl_seconds
        self._max_entries = max(1, cache_max_entries)
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._clock = clock

    async def read(
        self,
        url: str,
        *,
        max_chars: int = DEFAULT_MAX_CHARS,
        start: int = 0,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchPage:
        if max_chars < 1:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)
        if start < 0:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)

        cached = self._cache.get(url)
        now = self._clock()
        if cached is not None and cached.expires_at > now:
            self._cache.move_to_end(url)
            source = cached.page_source
        else:
            if cached is not None:
                del self._cache[url]
            source = await self._fetch_full(url, context, execution)
            self._cache[url] = _CacheEntry(source, expires_at=now + self._ttl)
            self._cache.move_to_end(url)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

        total = len(source.content)
        if start > total:
            start = total
        chunk = source.content[start : start + max_chars]
        next_start = start + max_chars if start + max_chars < total else None
        return FetchPage(
            title=source.title,
            url=source.final_url,
            content=chunk,
            total_chars=total,
            start=start,
            next_start=next_start,
            egress="direct",
            sources=source.providers,
        )

    async def _fetch_full(
        self,
        url: str,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchPageSource:
        request = FetchRequest(targets=(url,))
        batch = await self._module.fetch(request, context, execution)
        result = batch.items[0]
        if result.status != "success" or result.content is None:
            raise _reader_error(result.error)
        providers = tuple(
            provenance.provider
            for provenance in result.provenance
            if provenance.outcome == "success"
        ) or ((result.provenance[0].provider,) if result.provenance else ("builtin-fetch",))
        return FetchPageSource(
            title=result.title,
            final_url=str(result.final_url) if result.final_url is not None else url,
            content=result.content,
            providers=providers,
        )


def _reader_error(error) -> ProviderError:
    provider_id = error.provider if error is not None else None
    code = error.code if error is not None else "provider_unavailable"
    if code == "rate_limited":
        resolved = ProviderErrorCode.RATE_LIMITED
    elif code == "provider_timeout":
        resolved = ProviderErrorCode.DEADLINE_EXCEEDED
    elif code == "policy_blocked":
        resolved = ProviderErrorCode.POLICY_BLOCKED
    elif code == "invalid_request":
        resolved = ProviderErrorCode.INVALID_REQUEST
    else:
        resolved = ProviderErrorCode.PROVIDER_UNAVAILABLE
    return ProviderError(resolved, provider_id=provider_id)


def format_fetch_page(page: FetchPage) -> str:
    """Metadata head line, body slice, and the continuation tail when cut."""

    header = (
        f"title: {page.title or '(untitled)'} | url: {page.url} | "
        f"chars: {page.start + 1}-{page.start + len(page.content)} of {page.total_chars} "
        f"| egress: {page.egress}"
    )
    lines = [header, page.content]
    if page.next_start is not None:
        lines.append(f"[truncated — call fetch again with start={page.next_start} to continue]")
    return "\n".join(lines)


def format_fetch_error(error: ProviderError) -> str:
    """One actionable sentence for a failed fetch, naming what was tried."""

    tried = error.provider_id or "builtin-fetch"
    hint = "retry later, try another URL form, or pick a fetch source explicitly"
    return f"Fetch failed via {tried} ({error.code.value}). To proceed: {hint}."


__all__ = [
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_MAX_CHARS",
    "FetchPage",
    "FetchReaderService",
    "format_fetch_error",
    "format_fetch_page",
]
