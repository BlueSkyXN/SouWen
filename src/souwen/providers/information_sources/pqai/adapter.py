"""Provider v2 bridge for the existing authenticated PQAI client."""

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

from .spec import PQAI_BRIDGE_SPEC

_PROVIDER_ID = "pqai"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")


class PqaiClientProtocol(Protocol):
    async def search(self, query: str, n_results: int = 10) -> Any: ...
    async def close(self) -> None: ...


class PqaiSearchProvider(LegacySearchProvider):
    capability = "search"

    def __init__(self, client: PqaiClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, n_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != _PROVIDER_ID
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or total != len(results)
        or len(results) > limit
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
    ):
        raise ValueError("invalid PQAI response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    identifier = _required(getattr(value, "patent_id", None))
    if getattr(value, "source", None) != _PROVIDER_ID or _IDENTIFIER.fullmatch(identifier) is None:
        raise ValueError("invalid PQAI patent")
    parsed = urlsplit(_required(getattr(value, "source_url", None)))
    if (
        parsed.scheme,
        parsed.hostname,
        parsed.path,
        parsed.username,
        parsed.password,
        parsed.port,
        parsed.query,
        parsed.fragment,
    ) != ("https", "patents.google.com", f"/patent/{identifier}", None, None, None, "", ""):
        raise ValueError("invalid PQAI record URL")
    date = getattr(value, "publication_date", None)
    year = getattr(date, "year", None) if date is not None else None
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid PQAI year")
    return SearchItem(
        id=f"pqai:{identifier}",
        title=_required(getattr(value, "title", None)),
        url=f"https://patents.google.com/patent/{identifier}",
        snippet=_optional(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            identifiers=(SearchIdentifier(scheme="pqai", value=identifier),),
            resource_type="patent",
        ),
    )


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _required(value: Any) -> str:
    result = _optional(value)
    if result is None:
        raise ValueError("missing text")
    return result


_BRIDGE = LegacySearchSpec(_PROVIDER_ID, "patent", _invoke, _project)
assert PQAI_BRIDGE_SPEC.adapter_kind == "legacy_bridge"

__all__ = ["PqaiClientProtocol", "PqaiSearchProvider"]
