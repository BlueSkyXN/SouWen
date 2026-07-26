"""Provider v2 bridge preserving the legacy Google Patents scraper behavior."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

from souwen.platform.provider_spi import (
    PageInfo,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)
from souwen.platform.provider_spec import LegacySearchProvider, LegacySearchSpec

from .spec import GOOGLE_PATENTS_BRIDGE_SPEC

_PROVIDER_ID = "google_patents"
_PATENT_ID = re.compile(r"^[A-Z0-9]+$")


class GooglePatentsClientProtocol(Protocol):
    async def search(self, query: str, num_results: int = 10) -> Any: ...
    async def close(self) -> None: ...


class GooglePatentsSearchProvider(LegacySearchProvider):
    """Search bridge; XHR/HTML/browser fallback stays inside the legacy client."""

    capability = "search"

    def __init__(self, client: GooglePatentsClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE_SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, num_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy response source")
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid legacy search results")
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid legacy result total")
    if getattr(response, "page", None) != 1 or getattr(response, "per_page", None) != limit:
        raise ValueError("legacy Google Patents page does not match canonical request")
    return SearchPage(
        items=tuple(_item(value, index) for index, value in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    if getattr(value, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy patent source")
    identifier = _text(getattr(value, "patent_id", None)).upper()
    if _PATENT_ID.fullmatch(identifier) is None:
        raise ValueError("invalid Google patent identifier")
    parsed = urlsplit(_text(getattr(value, "source_url", None)))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "patents.google.com"
        or parsed.username
        or parsed.password
        or parsed.port
        or not parsed.path.startswith(f"/patent/{identifier}")
    ):
        raise ValueError("invalid Google Patents record URL")
    published = getattr(value, "publication_date", None)
    year = getattr(published, "year", None)
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid publication year")
    return SearchItem(
        id=f"google_patents:{identifier}",
        title=_text(getattr(value, "title", None)),
        url=f"https://patents.google.com{parsed.path}",
        snippet=_optional_text(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            identifiers=(SearchIdentifier(scheme="google_patents", value=identifier),),
            resource_type="patent",
        ),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _text(value: Any) -> str:
    result = _optional_text(value)
    if result is None:
        raise ValueError("missing text")
    return result


_BRIDGE_SPEC = LegacySearchSpec(_PROVIDER_ID, "patent", _invoke, _project)
assert GOOGLE_PATENTS_BRIDGE_SPEC.adapter_kind == "legacy_bridge"

__all__ = ["GooglePatentsClientProtocol", "GooglePatentsSearchProvider"]
