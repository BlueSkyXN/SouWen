"""Provider v2 Search bridge for the legacy anonymous OSTI client."""

from __future__ import annotations

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

from .spec import OSTI_BRIDGE_SPEC

_PROVIDER_ID = "osti"


class OstiClientProtocol(Protocol):
    async def search(self, query: str, rows: int = 10, page: int = 1) -> Any: ...
    async def close(self) -> None: ...


class OstiSearchProvider(LegacySearchProvider):
    capability = "search"

    def __init__(self, client: OstiClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE_SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, rows=limit, page=1)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy response source")
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid OSTI search results")
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid OSTI result total")
    if getattr(response, "page", None) != 1 or getattr(response, "per_page", None) != limit:
        raise ValueError("legacy OSTI page does not match canonical request")
    return SearchPage(
        items=tuple(_item(value, index) for index, value in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    if getattr(value, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy OSTI paper source")
    raw = getattr(value, "raw", None)
    identifier = raw.get("osti_id") if isinstance(raw, dict) else None
    if not isinstance(identifier, str) or not identifier.isdecimal():
        raise ValueError("invalid OSTI record identifier")
    parsed = urlsplit(_text(getattr(value, "source_url", None)))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.osti.gov"
        or parsed.path != f"/biblio/{identifier}"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid OSTI record URL")
    year = getattr(value, "year", None)
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid OSTI year")
    authors = tuple(
        _text(getattr(author, "name", None)) for author in getattr(value, "authors", ())
    )
    if len(authors) != len(set(authors)):
        raise ValueError("duplicate OSTI authors")
    return SearchItem(
        id=f"osti:{identifier}",
        title=_text(getattr(value, "title", None)),
        url=f"https://www.osti.gov/biblio/{identifier}",
        snippet=_optional_text(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            authors=authors,
            identifiers=(SearchIdentifier(scheme="osti", value=identifier),),
            resource_type=_optional_text(raw.get("product_type")),
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


_BRIDGE_SPEC = LegacySearchSpec(_PROVIDER_ID, "paper", _invoke, _project)
assert OSTI_BRIDGE_SPEC.adapter_kind == "legacy_bridge"

__all__ = ["OstiClientProtocol", "OstiSearchProvider"]
