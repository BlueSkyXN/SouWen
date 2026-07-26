"""Provider v2 bridge for Zenodo's legacy client."""

from __future__ import annotations
import re
from collections.abc import Sequence
from typing import Any, Protocol
from souwen.platform.provider_spec import LegacySearchProvider, LegacySearchSpec
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

_ID = re.compile(r"^[1-9][0-9]*$")


class ZenodoClientProtocol(Protocol):
    async def search(self, query: str, size: int = 10) -> Any: ...


class ZenodoSearchProvider(LegacySearchProvider):
    def __init__(self, client: ZenodoClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, size=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "zenodo"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid Zenodo response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("zenodo",), succeeded=("zenodo",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    identifier = str(getattr(paper, "raw", {}).get("zenodo_id", ""))
    if (
        getattr(paper, "source", None) != "zenodo"
        or _ID.fullmatch(identifier) is None
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid Zenodo item")
    return SearchItem(
        id=f"zenodo:{identifier}",
        title=paper.title.strip(),
        url=f"https://zenodo.org/records/{identifier}",
        snippet=_text(paper.abstract),
        rank=rank,
        provenance=(Provenance(provider="zenodo", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(paper.year),
            authors=_authors(paper),
            identifiers=(SearchIdentifier(scheme="zenodo", value=identifier),),
            resource_type=_text(getattr(paper, "raw", {}).get("resource_subtype")),
        ),
    )


def _text(v: Any) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str) or not v.strip():
        raise ValueError("invalid text")
    return v.strip()


def _year(v: Any) -> int | None:
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 9999:
        raise ValueError("invalid year")
    return v


def _authors(paper: Any) -> tuple[str, ...]:
    values = tuple(_text(getattr(author, "name", None)) for author in getattr(paper, "authors", ()))
    if any(value is None for value in values) or len(set(values)) != len(values):
        raise ValueError("invalid authors")
    return tuple(value for value in values if value is not None)


_SPEC = LegacySearchSpec("zenodo", "paper", _invoke, _project)
