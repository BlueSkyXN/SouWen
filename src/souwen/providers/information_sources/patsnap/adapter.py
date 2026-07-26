"""Provider v2 bridge for the existing authenticated PatSnap client."""

from __future__ import annotations

import re
from collections.abc import Sequence
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
from souwen.platform.provider_spec import ClientSearchProvider, ClientSearchSpec

from .spec import PATSNAP_BRIDGE_SPEC

_PROVIDER_ID = "patsnap"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")


class PatSnapClientProtocol(Protocol):
    async def search(self, query: str, limit: int = 10, offset: int = 0) -> Any: ...
    async def close(self) -> None: ...


class PatSnapSearchProvider(ClientSearchProvider):
    capability = "search"

    def __init__(self, client: PatSnapClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, limit=limit, offset=0)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results = _response_results(response, limit)
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=response.total_results),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _response_results(response: Any, limit: int) -> Sequence[Any]:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != _PROVIDER_ID
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
    ):
        raise ValueError("invalid PatSnap response")
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
    ):
        raise ValueError("invalid PatSnap response page")
    return results


def _item(value: Any, rank: int) -> SearchItem:
    identifier = _required(getattr(value, "patent_id", None))
    if getattr(value, "source", None) != _PROVIDER_ID or _IDENTIFIER.fullmatch(identifier) is None:
        raise ValueError("invalid PatSnap patent")
    url = _url(getattr(value, "source_url", None), "connect.patsnap.com", f"/patent/{identifier}")
    date = getattr(value, "publication_date", None)
    year = getattr(date, "year", None) if date is not None else None
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid PatSnap year")
    return SearchItem(
        id=f"patsnap:{identifier}",
        title=_required(getattr(value, "title", None)),
        url=url,
        snippet=_optional(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            identifiers=(SearchIdentifier(scheme="patsnap", value=identifier),),
            resource_type="patent",
        ),
    )


def _url(value: Any, host: str, path: str) -> str:
    parsed = urlsplit(_required(value))
    if (
        parsed.scheme,
        parsed.hostname,
        parsed.path,
        parsed.username,
        parsed.password,
        parsed.port,
        parsed.query,
        parsed.fragment,
    ) != ("https", host, path, None, None, None, "", ""):
        raise ValueError("invalid PatSnap URL")
    return f"https://{host}{path}"


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _required(value: Any) -> str:
    result = _optional(value)
    if result is None:
        raise ValueError("missing text")
    return result


_BRIDGE = ClientSearchSpec(_PROVIDER_ID, "patent", _invoke, _project)
assert PATSNAP_BRIDGE_SPEC.adapter_kind == "client_adapter"

__all__ = ["PatSnapClientProtocol", "PatSnapSearchProvider"]
