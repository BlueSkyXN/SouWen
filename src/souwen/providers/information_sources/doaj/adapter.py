"""Provider v2 bridge for the existing DOAJ article client."""

from __future__ import annotations
import re
from collections.abc import Sequence
from typing import Any, Protocol
from souwen.platform.provider_spec import ClientSearchProvider, ClientSearchSpec
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

_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class DoajClientProtocol(Protocol):
    async def search(self, query: str, page_size: int = 10, page: int = 1) -> Any: ...


class DoajSearchProvider(ClientSearchProvider):
    def __init__(self, client: DoajClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, page_size=limit, page=1)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "doaj"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid DOAJ response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("doaj",), succeeded=("doaj",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    identifier = getattr(paper, "raw", {}).get("doaj_id")
    if (
        getattr(paper, "source", None) != "doaj"
        or not isinstance(identifier, str)
        or _ID.fullmatch(identifier) is None
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid DOAJ item")
    return SearchItem(
        id=f"doaj:{identifier}",
        title=paper.title.strip(),
        url=f"https://doaj.org/article/{identifier}",
        snippet=_text(paper.abstract),
        rank=rank,
        provenance=(Provenance(provider="doaj", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(paper.year),
            authors=_authors(paper),
            identifiers=(SearchIdentifier(scheme="doaj", value=identifier),),
        ),
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _year(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid year")
    return value


def _authors(paper: Any) -> tuple[str, ...]:
    authors = tuple(
        _text(getattr(author, "name", None)) for author in getattr(paper, "authors", ())
    )
    if any(author is None for author in authors) or len(set(authors)) != len(authors):
        raise ValueError("invalid authors")
    return tuple(author for author in authors if author is not None)


_SPEC = ClientSearchSpec("doaj", "paper", _invoke, _project)
