"""Provider v2 adapter for the injected anonymous ERIC client."""

from __future__ import annotations

import asyncio
import inspect
import re
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


_PROVIDER_ID = "eric"
_ERIC_ID_PATTERN = re.compile(r"^[A-Z]{2}[0-9]+$")


class EricClientProtocol(Protocol):
    """Minimal legacy ERIC client surface injected by the composition root."""

    async def search(self, query: str, rows: int = 10, start: int = 0) -> Any:
        """Return a normalized legacy ``SearchResponse`` compatible object."""

    async def close(self) -> None:
        """Close the explicitly injected transport."""


class EricSearchProvider:
    """Search-only Provider v2 adapter for official ERIC metadata."""

    capability = "search"

    def __init__(self, client: EricClientProtocol, *, enabled: bool = True) -> None:
        self._client = client
        self._enabled = enabled
        self._closed = False

    async def search(
        self,
        request: SearchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> SearchPage:
        """Execute one bounded first-page ERIC search and canonicalize the response."""
        execution.raise_if_cancelled_or_expired()
        if self._closed or not self._enabled:
            raise ProviderError(ProviderErrorCode.INVALID_CONFIG, provider_id=_PROVIDER_ID)
        if request.domains != ("paper",):
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=_PROVIDER_ID)
        if request.page is not None and request.page.cursor is not None:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=_PROVIDER_ID)
        if request.filters is not None and request.filters.model_dump(exclude_none=True):
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=_PROVIDER_ID)

        limit = request.page.limit if request.page is not None else 10
        try:
            response = await _await_with_execution(
                self._client.search(request.query, rows=limit, start=0),
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
        """Report local eligibility without issuing a network request."""
        execution.raise_if_cancelled_or_expired()
        return ProviderProbe(
            provider=_PROVIDER_ID,
            capability="search",
            status="unavailable" if self._closed or not self._enabled else "available",
        )

    async def close(self) -> None:
        """Close the injected client once and remain retryable if cancellation interrupts close."""
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


def _to_search_page(response: Any, *, limit: int, context: RequestContext) -> SearchPage:
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
    if len(results) > limit:
        raise ValueError("legacy result count exceeds canonical limit")
    if total is not None and total < len(results):
        raise ValueError("legacy result total is smaller than the returned page")

    items = tuple(_to_search_item(item, rank=index) for index, item in enumerate(results, 1))
    return SearchPage(
        items=items,
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _to_search_item(paper: Any, *, rank: int) -> SearchItem:
    if getattr(paper, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy paper source")
    raw = getattr(paper, "raw", None)
    if not isinstance(raw, Mapping):
        raise ValueError("invalid legacy paper attributes")
    eric_id = _eric_id(raw.get("eric_id"))
    source_url = _eric_url(getattr(paper, "source_url", None), eric_id)

    publication_types = _string_tuple(raw.get("publication_types"))
    languages = _string_tuple(raw.get("language"))
    fulltext = raw.get("fulltext_authorized")
    if fulltext is not None and not isinstance(fulltext, bool):
        raise ValueError("invalid ERIC fulltext flag")

    return SearchItem(
        id=f"eric:{eric_id}",
        title=_required_text(getattr(paper, "title", None)),
        url=source_url,
        snippet=_optional_text(getattr(paper, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_optional_int(getattr(paper, "year", None)),
            authors=_author_names(getattr(paper, "authors", None)),
            identifiers=(SearchIdentifier(scheme="eric", value=eric_id),),
            resource_type=publication_types[0] if publication_types else None,
            language=languages[0] if languages else None,
            open_access=fulltext,
        ),
    )


def _eric_id(value: Any) -> str:
    identifier = _required_text(value).upper()
    if _ERIC_ID_PATTERN.fullmatch(identifier) is None:
        raise ValueError("invalid ERIC identifier")
    return identifier


def _eric_url(value: Any, eric_id: str) -> str:
    url = _required_text(value)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "eric.ed.gov"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path != "/"
        or parsed.fragment
        or parsed.query != f"id={eric_id}"
    ):
        raise ValueError("invalid ERIC record URL")
    return f"https://eric.ed.gov/?id={eric_id}"


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


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid integer")
    return value


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("invalid string sequence")
    normalized = tuple(_required_text(item) for item in value)
    if len(normalized) != len(set(normalized)):
        raise ValueError("duplicate string sequence")
    return normalized


def _author_names(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("invalid author sequence")
    names = tuple(_required_text(getattr(author, "name", None)) for author in value)
    if len(names) != len(set(names)):
        raise ValueError("duplicate authors")
    return names


__all__ = ["EricClientProtocol", "EricSearchProvider"]
