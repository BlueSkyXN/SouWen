"""Provider v2 adapter for the injected authenticated PatentsView client."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
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


_PROVIDER_ID = "patentsview"
_PATENT_ID_PATTERN = re.compile(r"^[A-Z0-9]+$")


class PatentsViewClientProtocol(Protocol):
    """Minimal PatentsView client surface injected by the composition root."""

    async def search(
        self,
        query: dict[str, Any],
        fields: list[str] | None = None,
        per_page: int = 10,
        page: int = 1,
        sort: list[dict[str, str]] | None = None,
    ) -> Any:
        """Return a normalized legacy ``SearchResponse`` compatible object."""

    async def close(self) -> None:
        """Close the explicitly injected transport."""


class PatentsViewSearchProvider(LegacySearchProvider):
    """Search-only Provider v2 adapter for authenticated USPTO patent metadata."""

    capability = "search"

    def __init__(self, client: PatentsViewClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _PATENTSVIEW_BRIDGE_SPEC, enabled=enabled)


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


def _to_search_item(patent: Any, *, rank: int) -> SearchItem:
    if getattr(patent, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy patent source")
    raw = getattr(patent, "raw", None)
    if not isinstance(raw, Mapping):
        raise ValueError("invalid legacy patent attributes")
    patent_id = _patent_id(getattr(patent, "patent_id", None))
    source_url = _patent_url(getattr(patent, "source_url", None), patent_id)
    publication_date = getattr(patent, "publication_date", None)
    year = getattr(publication_date, "year", None) if publication_date is not None else None

    return SearchItem(
        id=f"patentsview:{patent_id}",
        title=_required_text(getattr(patent, "title", None)),
        url=source_url,
        snippet=_optional_text(getattr(patent, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_optional_year(year),
            identifiers=(SearchIdentifier(scheme="patentsview", value=patent_id),),
            resource_type="patent",
        ),
    )


def _patent_id(value: Any) -> str:
    identifier = _required_text(value).upper()
    if _PATENT_ID_PATTERN.fullmatch(identifier) is None:
        raise ValueError("invalid USPTO patent identifier")
    return identifier


def _patent_url(value: Any, patent_id: str) -> str:
    parsed = urlsplit(_required_text(value))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "search.patentsview.org"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path != f"/patent/{patent_id}"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid PatentsView record URL")
    return f"https://search.patentsview.org/patent/{patent_id}"


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


def _optional_year(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid publication year")
    return value


async def _bridge_invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(
        {"_contains": {"patent_title": request.query}}, per_page=limit, page=1
    )


def _bridge_project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    return _to_search_page(response, limit=limit, context=context)


_PATENTSVIEW_BRIDGE_SPEC = LegacySearchSpec(
    "patentsview", "patent", _bridge_invoke, _bridge_project
)
__all__ = ["PatentsViewClientProtocol", "PatentsViewSearchProvider"]
