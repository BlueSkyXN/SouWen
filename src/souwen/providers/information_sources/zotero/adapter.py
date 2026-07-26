"""Provider v2 bridge for the configured Zotero library client."""

from __future__ import annotations
import re
from collections.abc import Mapping, Sequence
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

_KEY = re.compile(r"^[A-Za-z0-9]{8}$")
_LIBRARY = re.compile(r"^[A-Za-z0-9_-]+$")


class ZoteroClientProtocol(Protocol):
    async def search(
        self,
        query: str,
        qmode: str = "everything",
        tag: str | None = None,
        limit: int = 10,
        start: int = 0,
    ) -> Any: ...


class ZoteroSearchProvider(LegacySearchProvider):
    def __init__(self, client: ZoteroClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, qmode="everything", tag=None, limit=limit, start=0)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "zotero"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid Zotero response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("zotero",), succeeded=("zotero",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    raw = getattr(paper, "raw", None)
    key = raw.get("item_key") if isinstance(raw, Mapping) else None
    library_id = raw.get("library_id") if isinstance(raw, Mapping) else None
    library_type = raw.get("library_type") if isinstance(raw, Mapping) else None
    if (
        getattr(paper, "source", None) != "zotero"
        or not isinstance(key, str)
        or _KEY.fullmatch(key) is None
        or not isinstance(library_id, str)
        or _LIBRARY.fullmatch(library_id) is None
        or library_type not in {"user", "group"}
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid Zotero item")
    collection = "users" if library_type == "user" else "groups"
    url = f"https://api.zotero.org/{collection}/{library_id}/items/{key}"
    return SearchItem(
        id=f"zotero:{key}",
        title=paper.title.strip(),
        url=url,
        snippet=_text(paper.abstract),
        rank=rank,
        provenance=(Provenance(provider="zotero", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(paper.year),
            authors=_authors(paper),
            identifiers=(SearchIdentifier(scheme="zotero", value=key),),
            resource_type=_text(getattr(paper, "raw", {}).get("item_type")),
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


_SPEC = LegacySearchSpec("zotero", "paper", _invoke, _project)
