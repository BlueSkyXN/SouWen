"""Provider v2 bridge for the existing authenticated The Lens client."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

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
from souwen.platform.provider_spec import LegacySearchProvider, LegacySearchSpec

from .spec import THE_LENS_BRIDGE_SPEC

_PROVIDER_ID = "the_lens"


class TheLensClientProtocol(Protocol):
    async def search_patents(self, query: str, size: int = 10, offset: int = 0) -> Any: ...
    async def close(self) -> None: ...


class TheLensSearchProvider(LegacySearchProvider):
    capability = "search"

    def __init__(self, client: TheLensClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search_patents(request.query, size=limit, offset=0)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != _PROVIDER_ID
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
    ):
        raise ValueError("invalid The Lens response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    raw = getattr(value, "raw", None)
    lens_id = raw.get("lens_id") if isinstance(raw, Mapping) else None
    if (
        getattr(value, "source", None) != _PROVIDER_ID
        or not isinstance(lens_id, str)
        or not lens_id.strip()
    ):
        raise ValueError("invalid The Lens identifier")
    parsed = urlsplit(_text(getattr(value, "source_url", None)))
    path = f"/lens/patent/{lens_id}"
    if (
        parsed.scheme,
        parsed.hostname,
        parsed.path,
        parsed.username,
        parsed.password,
        parsed.port,
        parsed.query,
        parsed.fragment,
    ) != ("https", "www.lens.org", path, None, None, None, "", ""):
        raise ValueError("invalid The Lens record URL")
    patent_id = _text(getattr(value, "patent_id", None))
    date = getattr(value, "publication_date", None)
    year = getattr(date, "year", None) if date else None
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid Lens year")
    return SearchItem(
        id=f"the_lens:{lens_id}",
        title=_text(getattr(value, "title", None)),
        url=f"https://www.lens.org{path}",
        snippet=_optional(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            identifiers=(
                SearchIdentifier(scheme="the_lens", value=lens_id),
                SearchIdentifier(scheme="patent", value=patent_id),
            ),
            resource_type="patent",
        ),
    )


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _text(value: Any) -> str:
    result = _optional(value)
    if result is None:
        raise ValueError("missing text")
    return result


_BRIDGE = LegacySearchSpec(_PROVIDER_ID, "patent", _invoke, _project)
assert THE_LENS_BRIDGE_SPEC.adapter_kind == "legacy_bridge"
__all__ = ["TheLensClientProtocol", "TheLensSearchProvider"]
