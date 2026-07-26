"""Provider v2 bridge for OpenAIRE's nested existing response."""

from __future__ import annotations
import re
from collections.abc import Mapping, Sequence
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
_PID = re.compile(r"^[A-Za-z0-9._:-]+$")


class OpenAireClientProtocol(Protocol):
    async def search(self, query: str, size: int = 10) -> Any: ...


class OpenAireSearchProvider(ClientSearchProvider):
    def __init__(self, client: OpenAireClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, size=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "openaire"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid OpenAIRE response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("openaire",), succeeded=("openaire",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    if (
        getattr(paper, "source", None) != "openaire"
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid OpenAIRE item")
    doi = getattr(paper, "doi", None)
    if isinstance(doi, str) and _DOI.fullmatch(doi):
        identifier, scheme, url = doi.lower(), "doi", f"https://doi.org/{doi}"
    else:
        raw = getattr(paper, "raw", None)
        openaire_id = raw.get("openaire_id") if isinstance(raw, Mapping) else None
        if not isinstance(openaire_id, str) or _PID.fullmatch(openaire_id) is None:
            raise ValueError("invalid OpenAIRE identifier")
        identifier, scheme, url = (
            openaire_id,
            "openaire",
            f"https://explore.openaire.eu/search/publication?pid={openaire_id}",
        )
    return SearchItem(
        id=f"{scheme}:{identifier}",
        title=paper.title.strip(),
        url=url,
        snippet=_text(paper.abstract),
        rank=rank,
        provenance=(Provenance(provider="openaire", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(paper.year),
            authors=_authors(paper),
            identifiers=(SearchIdentifier(scheme=scheme, value=identifier),),
            resource_type=_text(getattr(paper, "raw", {}).get("result_type")),
            language=_text(getattr(paper, "raw", {}).get("language")),
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


_SPEC = ClientSearchSpec("openaire", "paper", _invoke, _project)
