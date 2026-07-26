"""Provider v2 bridge for the existing arXiv Atom client."""

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

_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z0-9.-]*/\d{7})(?:v\d+)?$")


class ArxivClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...


class ArxivSearchProvider(LegacySearchProvider):
    def __init__(self, client: ArxivClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results = _response_items(response, limit)
    items = tuple(_item(paper, index) for index, paper in enumerate(results, 1))
    return SearchPage(
        items=items,
        page=PageInfo(limit=limit, total=response.total_results),
        meta=SearchMeta(requested=("arxiv",), succeeded=("arxiv",)),
        context=context,
    )


def _response_items(response: Any, limit: int) -> Sequence[Any]:
    results = getattr(response, "results", None)
    if (
        getattr(response, "source", None) != "arxiv"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
    ):
        raise ValueError("invalid arXiv response")
    total = getattr(response, "total_results", None)
    if not isinstance(total, int) or isinstance(total, bool) or total < len(results):
        raise ValueError("invalid arXiv total")
    return results


def _item(paper: Any, rank: int) -> SearchItem:
    if (
        getattr(paper, "source", None) != "arxiv"
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid arXiv item")
    parsed = urlsplit(getattr(paper, "source_url", ""))
    match = re.fullmatch(r"/abs/(.+)", parsed.path)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"arxiv.org", "www.arxiv.org"}
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
        or match is None
        or _ID.fullmatch(match.group(1)) is None
    ):
        raise ValueError("invalid arXiv identifier")
    identifier = match.group(1)
    return SearchItem(
        id=f"arxiv:{identifier}",
        title=paper.title.strip(),
        url=paper.source_url,
        snippet=paper.abstract,
        rank=rank,
        provenance=(Provenance(provider="arxiv", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=paper.year,
            authors=tuple(author.name for author in paper.authors),
            identifiers=(SearchIdentifier(scheme="arxiv", value=identifier),),
        ),
    )


_SPEC = LegacySearchSpec("arxiv", "paper", _invoke, _project)
