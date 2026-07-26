"""Provider v2 bridge for authenticated EPO OPS CQL Search."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

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
from .spec import EPO_OPS_BRIDGE_SPEC

_PROVIDER_ID = "epo_ops"


class EpoOpsClientProtocol(Protocol):
    async def search(self, cql_query: str, range_begin: int = 1, range_end: int = 10) -> Any: ...
    async def close(self) -> None: ...


class EpoOpsSearchProvider(LegacySearchProvider):
    capability = "search"

    def __init__(self, client: EpoOpsClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, range_begin=1, range_end=limit)


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
        raise ValueError("invalid EPO OPS response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    identifier = _text(getattr(value, "patent_id", None))
    if getattr(value, "source", None) != _PROVIDER_ID:
        raise ValueError("invalid EPO OPS patent")
    parsed = urlsplit(_text(getattr(value, "source_url", None)))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "worldwide.espacenet.com"
        or parsed.path != "/patent/search"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.fragment
        or parse_qs(parsed.query) != {"q": [identifier]}
    ):
        raise ValueError("invalid EPO OPS record URL")
    date = getattr(value, "publication_date", None)
    year = getattr(date, "year", None) if date else None
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid EPO OPS year")
    return SearchItem(
        id=f"epo_ops:{identifier}",
        title=_text(getattr(value, "title", None)),
        url=f"https://worldwide.espacenet.com/patent/search?q={identifier}",
        snippet=_optional(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            identifiers=(SearchIdentifier(scheme="epo_ops", value=identifier),),
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
assert EPO_OPS_BRIDGE_SPEC.adapter_kind == "legacy_bridge"
__all__ = ["EpoOpsClientProtocol", "EpoOpsSearchProvider"]
