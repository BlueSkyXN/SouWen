"""Provider v2 bridge for Crossref's existing client and DOI projection."""

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


class CrossrefClientProtocol(Protocol):
    async def search(self, query: str, rows: int = 10, offset: int = 0) -> Any: ...


class CrossrefSearchProvider(ClientSearchProvider):
    def __init__(self, client: CrossrefClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, rows=limit, offset=0)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "crossref"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid Crossref response")
    return SearchPage(
        items=tuple(_item(paper, index) for index, paper in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("crossref",), succeeded=("crossref",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    doi = getattr(paper, "doi", None)
    if (
        getattr(paper, "source", None) != "crossref"
        or not isinstance(doi, str)
        or _DOI.fullmatch(doi) is None
        or getattr(paper, "source_url", None) != f"https://doi.org/{doi}"
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid Crossref identifier")
    return SearchItem(
        id=f"doi:{doi.lower()}",
        title=paper.title.strip(),
        url=paper.source_url,
        snippet=paper.abstract,
        rank=rank,
        provenance=(Provenance(provider="crossref", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=paper.year,
            authors=tuple(author.name for author in paper.authors),
            identifiers=(SearchIdentifier(scheme="doi", value=doi),),
            resource_type=paper.raw.get("type"),
            citation_count=paper.citation_count,
        ),
    )


_SPEC = ClientSearchSpec("crossref", "paper", _invoke, _project)
