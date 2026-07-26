"""Provider v2 bridge for the local-filtering bioRxiv client."""

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


class BioRxivClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10) -> Any: ...


class BioRxivSearchProvider(ClientSearchProvider):
    def __init__(self, client: BioRxivClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, per_page=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results = getattr(response, "results", None)
    if (
        getattr(response, "source", None) != "biorxiv"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or getattr(response, "total_results", None) != len(results)
    ):
        raise ValueError("invalid bioRxiv response")
    items = tuple(_item(paper, index) for index, paper in enumerate(results, 1))
    return SearchPage(
        items=items,
        page=PageInfo(limit=limit, total=response.total_results),
        meta=SearchMeta(requested=("biorxiv",), succeeded=("biorxiv",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    doi = getattr(paper, "doi", None)
    if (
        getattr(paper, "source", None) != "biorxiv"
        or not isinstance(doi, str)
        or _DOI.fullmatch(doi) is None
        or getattr(paper, "source_url", None) != f"https://doi.org/{doi}"
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid bioRxiv identifier")
    return SearchItem(
        id=f"doi:{doi.lower()}",
        title=paper.title.strip(),
        url=paper.source_url,
        snippet=paper.abstract,
        rank=rank,
        provenance=(Provenance(provider="biorxiv", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=paper.year,
            authors=tuple(author.name for author in paper.authors),
            identifiers=(SearchIdentifier(scheme="doi", value=doi),),
            resource_type=paper.raw.get("type"),
        ),
    )


_SPEC = ClientSearchSpec("biorxiv", "paper", _invoke, _project)
