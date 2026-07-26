"""Provider v2 Search bridge for the legacy two-step PMC XML client."""

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

from .spec import PMC_BRIDGE_SPEC

_PROVIDER_ID = "pmc"
_PMCID = re.compile(r"^PMC\d+$")


class PmcClientProtocol(Protocol):
    async def search(self, query: str, retmax: int = 10, retstart: int = 0) -> Any: ...
    async def close(self) -> None: ...


class PmcSearchProvider(LegacySearchProvider):
    capability = "search"

    def __init__(self, client: PmcClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE_SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, retmax=limit, retstart=0)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy response source")
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid PMC search results")
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid PMC result total")
    if getattr(response, "page", None) != 1 or getattr(response, "per_page", None) != limit:
        raise ValueError("legacy PMC page does not match canonical request")
    return SearchPage(
        items=tuple(_item(value, index) for index, value in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    if getattr(value, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected legacy PMC paper source")
    raw = getattr(value, "raw", None)
    identifier = raw.get("pmcid") if isinstance(raw, dict) else None
    if not isinstance(identifier, str) or _PMCID.fullmatch(identifier) is None:
        raise ValueError("invalid PMCID")
    parsed = urlsplit(_text(getattr(value, "source_url", None)))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.ncbi.nlm.nih.gov"
        or parsed.path != f"/pmc/articles/{identifier}/"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid PMC record URL")
    year = getattr(value, "year", None)
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid PMC year")
    authors = tuple(
        _text(getattr(author, "name", None)) for author in getattr(value, "authors", ())
    )
    if len(authors) != len(set(authors)):
        raise ValueError("duplicate PMC authors")
    return SearchItem(
        id=f"pmc:{identifier}",
        title=_text(getattr(value, "title", None)),
        url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{identifier}/",
        snippet=_optional_text(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            authors=authors,
            identifiers=(SearchIdentifier(scheme="pmc", value=identifier),),
            open_access=True,
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
assert PMC_BRIDGE_SPEC.adapter_kind == "legacy_bridge"

__all__ = ["PmcClientProtocol", "PmcSearchProvider"]
