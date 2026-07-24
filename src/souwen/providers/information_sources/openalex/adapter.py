"""Provider v2 adapter that maps an injected legacy OpenAlex client to canonical Search."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any, Protocol
from urllib.parse import urlsplit

from souwen.common_runtime.errors import SouWenError
from souwen.common_runtime.transport.errors import RateLimitError, SourceUnavailableError
from souwen.platform.provider_spi import (
    ExecutionContext,
    PageInfo,
    ProviderError,
    ProviderErrorCode,
    ProviderProbe,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)


_PROVIDER_ID = "openalex"


class OpenAlexClientProtocol(Protocol):
    """The minimal legacy-client surface used by this target adapter."""

    async def search(
        self,
        query: str,
        filters: dict[str, str] | None = None,
        sort: str | None = None,
        page: int = 1,
        per_page: int = 10,
    ) -> Any:
        """Return a legacy ``SearchResponse`` compatible object."""


class OpenAlexSearchProvider:
    """Search-only provider that preserves legacy OpenAlex query behavior behind the SPI."""

    capability = "search"

    def __init__(self, client: OpenAlexClientProtocol, *, enabled: bool = True) -> None:
        self._client = client
        self._enabled = enabled
        self._closed = False

    async def search(
        self,
        request: SearchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> SearchPage:
        """Map canonical paper search to the legacy client's bounded first page."""
        execution.raise_if_cancelled_or_expired()
        if self._closed or not self._enabled:
            raise ProviderError(ProviderErrorCode.INVALID_CONFIG, provider_id=_PROVIDER_ID)
        if request.domains != ("paper",):
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=_PROVIDER_ID)
        if request.page is not None and request.page.cursor is not None:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=_PROVIDER_ID)

        limit = request.page.limit if request.page is not None else 10
        filters = _legacy_filters(request)
        try:
            response = await _await_with_execution(
                self._client.search(
                    request.query,
                    filters=filters,
                    sort=None,
                    page=1,
                    per_page=limit,
                ),
                execution,
            )
            execution.raise_if_cancelled_or_expired()
            return _to_search_page(response, limit=limit, context=context)
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except RateLimitError as exc:
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id=_PROVIDER_ID,
                retry_after_seconds=getattr(exc, "retry_after", None),
            ) from None
        except TimeoutError:
            raise ProviderError(
                ProviderErrorCode.DEADLINE_EXCEEDED, provider_id=_PROVIDER_ID
            ) from None
        except SourceUnavailableError:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE, provider_id=_PROVIDER_ID
            ) from None
        except SouWenError as exc:
            code = (
                ProviderErrorCode.INVALID_CONFIG
                if type(exc).__name__ == "ConfigError"
                else ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
            )
            raise ProviderError(code, provider_id=_PROVIDER_ID) from None
        except (AttributeError, TypeError, ValueError):
            raise ProviderError(
                ProviderErrorCode.INVALID_UPSTREAM_RESPONSE, provider_id=_PROVIDER_ID
            ) from None
        except Exception:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE, provider_id=_PROVIDER_ID
            ) from None

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        """Return bounded local readiness without issuing a billable/network probe."""
        execution.raise_if_cancelled_or_expired()
        return ProviderProbe(
            provider=_PROVIDER_ID,
            capability="search",
            status="unavailable" if self._closed or not self._enabled else "available",
        )

    async def close(self) -> None:
        """Close an owned injected client at most once when it exposes a close operation."""
        if self._closed:
            return
        self._closed = True
        closer = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if closer is None:
            return
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            self._closed = False
            raise


async def _await_with_execution(value: Any, execution: ExecutionContext) -> Any:
    """Apply the SPI deadline and live cancellation signal to the injected client call."""
    provider_task = asyncio.ensure_future(value)
    cancellation_task = asyncio.create_task(execution.cancel_event.wait())
    try:
        done, _pending = await asyncio.wait(
            {provider_task, cancellation_task},
            timeout=execution.remaining_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if provider_task in done:
            return await provider_task
        provider_task.cancel()
        with suppress(asyncio.CancelledError):
            await provider_task
        code = (
            ProviderErrorCode.CANCELLED
            if cancellation_task in done
            else ProviderErrorCode.DEADLINE_EXCEEDED
        )
        raise ProviderError(code, provider_id=_PROVIDER_ID)
    finally:
        cancellation_task.cancel()
        if not provider_task.done():
            provider_task.cancel()
        await asyncio.gather(provider_task, cancellation_task, return_exceptions=True)


def _legacy_filters(request: SearchRequest) -> dict[str, str] | None:
    """Map only canonical, reviewed filters in deterministic upstream parameter order."""
    if request.filters is None:
        return None
    filters: dict[str, str] = {}
    if request.filters.year_from is not None:
        filters["from_publication_date"] = f"{request.filters.year_from:04d}-01-01"
    if request.filters.year_to is not None:
        filters["to_publication_date"] = f"{request.filters.year_to:04d}-12-31"
    if request.filters.language is not None:
        filters["language"] = request.filters.language
    if request.filters.open_access is not None:
        filters["is_oa"] = "true" if request.filters.open_access else "false"
    if request.filters.resource_type is not None:
        filters["type"] = request.filters.resource_type
    return filters or None


def _to_search_page(response: Any, *, limit: int, context: RequestContext) -> SearchPage:
    """Strictly transform legacy ``SearchResponse`` / ``PaperResult`` data to canonical DTOs."""
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy response source")
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    response_page = getattr(response, "page", None)
    response_limit = getattr(response, "per_page", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid legacy search results")
    if total is not None and (not isinstance(total, int) or isinstance(total, bool) or total < 0):
        raise ValueError("invalid legacy result total")
    if response_page != 1 or response_limit != limit:
        raise ValueError("legacy page does not match canonical request")

    items = tuple(
        _to_search_item(paper, rank=index) for index, paper in enumerate(results, start=1)
    )
    return SearchPage(
        items=items,
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _to_search_item(paper: Any, *, rank: int) -> SearchItem:
    """Map one normalized legacy paper while retaining only canonical public metadata."""
    if getattr(paper, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy paper source")
    title = _required_text(getattr(paper, "title", None))
    doi = _normalise_doi(getattr(paper, "doi", None))
    source_url = _normalise_url(getattr(paper, "source_url", None))
    if doi is None and source_url is None:
        raise ValueError("paper lacks stable identifier")

    identifiers: list[SearchIdentifier] = []
    if doi is not None:
        identifiers.append(SearchIdentifier(scheme="doi", value=doi))
    if source_url is not None:
        identifiers.append(SearchIdentifier(scheme="openalex", value=source_url))
    item_id = f"doi:{doi.lower()}" if doi is not None else f"openalex:{source_url}"
    canonical_url = f"https://doi.org/{doi}" if doi is not None else source_url
    raw = getattr(paper, "raw", {})
    if not isinstance(raw, Mapping):
        raise ValueError("invalid legacy paper attributes")

    return SearchItem(
        id=item_id,
        title=title,
        url=canonical_url,
        snippet=_optional_text(getattr(paper, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_optional_int(getattr(paper, "year", None)),
            authors=_author_names(getattr(paper, "authors", None)),
            identifiers=tuple(identifiers),
            resource_type=_optional_text(raw.get("type")),
            open_access=raw.get("is_oa") if isinstance(raw.get("is_oa"), bool) else None,
            citation_count=_optional_nonnegative_int(getattr(paper, "citation_count", None)),
        ),
    )


def _required_text(value: Any) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError("missing required text")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid text")
    normalized = value.strip()
    return normalized or None


def _normalise_doi(value: Any) -> str | None:
    doi = _optional_text(value)
    if doi is None:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix) :]
            break
    doi = _required_text(doi)
    prefix, separator, suffix = doi.partition("/")
    if not separator or not prefix.startswith("10.") or not prefix[3:].isdigit() or not suffix:
        raise ValueError("invalid DOI")
    if any(character.isspace() for character in doi):
        raise ValueError("invalid DOI")
    return doi


def _normalise_url(value: Any) -> str | None:
    url = _optional_text(value)
    if url is None:
        return None
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "openalex.org"
        or not parsed.path.startswith("/W")
    ):
        raise ValueError("invalid OpenAlex source URL")
    return url


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid year")
    return value


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("invalid citation count")
    return value


def _author_names(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("invalid authors")
    names: list[str] = []
    for author in value:
        name = _required_text(getattr(author, "name", None))
        if name not in names:
            names.append(name)
    return tuple(names)


__all__ = ["OpenAlexClientProtocol", "OpenAlexSearchProvider"]
