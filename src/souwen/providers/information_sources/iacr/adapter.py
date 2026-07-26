"""Provider v2 bridge preserving legacy IACR HTML parsing."""

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

from .spec import IACR_BRIDGE_SPEC

_PROVIDER_ID = "iacr"
_PAPER_ID = re.compile(r"^\d{4}/\d+$")


class IacrClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...
    async def close(self) -> None: ...


class IacrSearchProvider(LegacySearchProvider):
    capability = "search"

    def __init__(self, client: IacrClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE_SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy response source")
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or total != len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid IACR search response")
    return SearchPage(
        items=tuple(_item(value, index) for index, value in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    if getattr(value, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy paper source")
    raw = getattr(value, "raw", None)
    identifier = raw.get("paper_id") if isinstance(raw, dict) else None
    if not isinstance(identifier, str) or _PAPER_ID.fullmatch(identifier) is None:
        raise ValueError("invalid IACR paper identifier")
    url = urlsplit(_text(getattr(value, "source_url", None)))
    if (
        url.scheme != "https"
        or url.hostname != "eprint.iacr.org"
        or url.path != f"/{identifier}"
        or url.username
        or url.password
        or url.port
        or url.query
        or url.fragment
    ):
        raise ValueError("invalid IACR record URL")
    year = getattr(value, "year", None)
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid paper year")
    authors = tuple(
        _text(getattr(author, "name", None)) for author in getattr(value, "authors", ())
    )
    if len(authors) != len(set(authors)):
        raise ValueError("duplicate IACR authors")
    return SearchItem(
        id=f"iacr:{identifier}",
        title=_text(getattr(value, "title", None)),
        url=f"https://eprint.iacr.org/{identifier}",
        snippet=_optional_text(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            authors=authors,
            identifiers=(SearchIdentifier(scheme="iacr", value=identifier),),
            resource_type="preprint",
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
assert IACR_BRIDGE_SPEC.adapter_kind == "legacy_bridge"

__all__ = ["IacrClientProtocol", "IacrSearchProvider"]
