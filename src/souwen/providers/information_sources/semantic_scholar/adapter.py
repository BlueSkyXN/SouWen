"""Provider v2 bridge for Semantic Scholar's existing client."""

from __future__ import annotations
import re
from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit
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


class SemanticScholarClientProtocol(Protocol):
    async def search(
        self, query: str, fields: str | None = None, limit: int = 10, offset: int = 0
    ) -> Any: ...


class SemanticScholarSearchProvider(ClientSearchProvider):
    def __init__(self, client: SemanticScholarClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, fields=None, limit=limit, offset=0)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "semantic_scholar"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid Semantic Scholar response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("semantic_scholar",), succeeded=("semantic_scholar",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    parsed = urlsplit(getattr(paper, "source_url", ""))
    match = re.fullmatch(r"/paper/([A-Za-z0-9_-]+)", parsed.path)
    if (
        getattr(paper, "source", None) != "semantic_scholar"
        or parsed.scheme != "https"
        or parsed.hostname != "www.semanticscholar.org"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
        or match is None
        or _ID.fullmatch(match.group(1)) is None
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid Semantic Scholar item")
    identifier = match.group(1)
    return SearchItem(
        id=f"semantic_scholar:{identifier}",
        title=paper.title.strip(),
        url=f"https://www.semanticscholar.org/paper/{identifier}",
        snippet=_text(paper.abstract),
        rank=rank,
        provenance=(Provenance(provider="semantic_scholar", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(paper.year),
            authors=_authors(paper),
            identifiers=(SearchIdentifier(scheme="semantic_scholar", value=identifier),),
            open_access=getattr(paper, "raw", {}).get("is_open_access"),
            citation_count=_count(paper.citation_count),
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


def _count(v: Any) -> int | None:
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise ValueError("invalid count")
    return v


def _authors(paper: Any) -> tuple[str, ...]:
    values = tuple(_text(getattr(author, "name", None)) for author in getattr(paper, "authors", ()))
    if any(value is None for value in values) or len(set(values)) != len(values):
        raise ValueError("invalid authors")
    return tuple(value for value in values if value is not None)


_SPEC = ClientSearchSpec("semantic_scholar", "paper", _invoke, _project)
