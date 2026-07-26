"""Provider v2 bridge for CORE's existing work search client."""

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

_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
_CORE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class CoreClientProtocol(Protocol):
    async def search(self, query: str, limit: int = 10, offset: int = 0) -> Any: ...


class CoreSearchProvider(ClientSearchProvider):
    def __init__(self, client: CoreClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, limit=limit, offset=0)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "core"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid CORE response")
    return SearchPage(
        items=tuple(_item(value, rank) for rank, value in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("core",), succeeded=("core",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    if (
        getattr(paper, "source", None) != "core"
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid CORE item")
    doi = getattr(paper, "doi", None)
    if isinstance(doi, str) and _DOI.fullmatch(doi):
        identifier, url, scheme = doi.lower(), f"https://doi.org/{doi}", "doi"
    else:
        raw = getattr(paper, "raw", None)
        core_id = raw.get("core_id") if isinstance(raw, dict) else None
        if not isinstance(core_id, str) or _CORE_ID.fullmatch(core_id) is None:
            raise ValueError("invalid CORE identifier")
        identifier, url, scheme = core_id, f"https://core.ac.uk/works/{core_id}", "core"
    return SearchItem(
        id=f"{scheme}:{identifier}",
        title=paper.title.strip(),
        url=url,
        snippet=_optional(paper.abstract),
        rank=rank,
        provenance=(Provenance(provider="core", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(paper.year),
            authors=_authors(paper),
            identifiers=(SearchIdentifier(scheme=scheme, value=identifier),),
            language=_optional(paper.raw.get("language")),
            citation_count=_count(paper.citation_count),
        ),
    )


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid text")
    return value.strip() or None


def _authors(paper: Any) -> tuple[str, ...]:
    values = tuple(
        _optional(getattr(author, "name", None)) for author in getattr(paper, "authors", ())
    )
    if any(value is None for value in values) or len(set(values)) != len(values):
        raise ValueError("invalid authors")
    return tuple(value for value in values if value is not None)


def _year(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid year")
    return value


def _count(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("invalid count")
    return value


_SPEC = ClientSearchSpec("core", "paper", _invoke, _project)
