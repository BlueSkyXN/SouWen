"""Provider v2 bridge for Europe PMC's legacy client."""

from __future__ import annotations
import re
from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

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

_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class EuropePmcClientProtocol(Protocol):
    async def search(self, query: str, page_size: int = 10) -> Any: ...


class EuropePmcSearchProvider(LegacySearchProvider):
    def __init__(self, client: EuropePmcClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, page_size=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "europepmc"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid Europe PMC response")
    return SearchPage(
        items=tuple(_item(paper, index) for index, paper in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("europepmc",), succeeded=("europepmc",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    identifier = getattr(paper, "raw", {}).get("id")
    parsed = urlsplit(getattr(paper, "source_url", ""))
    if (
        getattr(paper, "source", None) != "europepmc"
        or not isinstance(identifier, str)
        or _ID.fullmatch(identifier) is None
        or parsed.scheme != "https"
        or parsed.hostname != "europepmc.org"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.fragment
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid Europe PMC identifier")
    return SearchItem(
        id=f"europepmc:{identifier}",
        title=paper.title.strip(),
        url=paper.source_url,
        snippet=paper.abstract,
        rank=rank,
        provenance=(Provenance(provider="europepmc", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=paper.year,
            authors=tuple(author.name for author in paper.authors),
            identifiers=(SearchIdentifier(scheme="europepmc", value=identifier),),
            open_access=paper.raw.get("is_open_access"),
            citation_count=paper.citation_count,
        ),
    )


_SPEC = LegacySearchSpec("europepmc", "paper", _invoke, _project)
