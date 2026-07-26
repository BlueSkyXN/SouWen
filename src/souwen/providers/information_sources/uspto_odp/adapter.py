"""Provider v2 bridge for the existing authenticated USPTO ODP client."""

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

from .spec import USPTO_ODP_BRIDGE_SPEC

_PROVIDER_ID = "uspto_odp"


class UsptoOdpClientProtocol(Protocol):
    async def search_applications(self, query: str, per_page: int = 10, offset: int = 0) -> Any: ...
    async def close(self) -> None: ...


class UsptoOdpSearchProvider(LegacySearchProvider):
    capability = "search"

    def __init__(self, client: UsptoOdpClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search_applications(request.query, per_page=limit, offset=0)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != _PROVIDER_ID
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
    ):
        raise ValueError("invalid USPTO ODP response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    identifier = _text(getattr(value, "patent_id", None))
    if getattr(value, "source", None) != _PROVIDER_ID:
        raise ValueError("invalid USPTO patent")
    parsed = urlsplit(_text(getattr(value, "source_url", None)))
    if (
        parsed.scheme,
        parsed.hostname,
        parsed.path,
        parsed.username,
        parsed.password,
        parsed.port,
        parsed.query,
        parsed.fragment,
    ) != ("https", "data.uspto.gov", f"/patent/{identifier}", None, None, None, "", ""):
        raise ValueError("invalid USPTO ODP record URL")
    date = getattr(value, "publication_date", None)
    year = getattr(date, "year", None) if date else None
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid USPTO year")
    return SearchItem(
        id=f"uspto_odp:{identifier}",
        title=_text(getattr(value, "title", None)),
        url=f"https://data.uspto.gov/patent/{identifier}",
        snippet=_optional(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            identifiers=(SearchIdentifier(scheme="uspto_odp", value=identifier),),
            resource_type="patent",
        ),
    )


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _text(value: Any) -> str:
    result = _optional(value)
    if result is None:
        raise ValueError("missing text")
    return result


_BRIDGE = LegacySearchSpec(_PROVIDER_ID, "patent", _invoke, _project)
assert USPTO_ODP_BRIDGE_SPEC.adapter_kind == "legacy_bridge"
__all__ = ["UsptoOdpClientProtocol", "UsptoOdpSearchProvider"]
