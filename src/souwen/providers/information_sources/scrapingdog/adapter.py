"""Provider v2 bridge for scrapingdog's existing web Search client."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

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

_PROVIDER_ID = "scrapingdog"


class ScrapingDogClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...


class ScrapingDogSearchProvider(ClientSearchProvider):
    def __init__(self, client: ScrapingDogClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != _PROVIDER_ID
        or getattr(response, "page", None) != 1
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid existing web search response")
    return SearchPage(
        items=tuple(_item(result, rank) for rank, result in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(result: Any, rank: int) -> SearchItem:
    if (
        getattr(result, "source", None) != _PROVIDER_ID
        or not isinstance(getattr(result, "title", None), str)
        or not result.title.strip()
    ):
        raise ValueError("invalid existing web result")
    url = _canonical_url(getattr(result, "url", None))
    identifier = sha256(url.encode("utf-8")).hexdigest()
    return SearchItem(
        id=f"{_PROVIDER_ID}:{identifier}",
        title=result.title.strip(),
        url=url,
        snippet=_optional_text(getattr(result, "snippet", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            identifiers=(SearchIdentifier(scheme=_PROVIDER_ID, value=identifier),)
        ),
    )


def _canonical_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing record URL")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("invalid record URL")
    host = parsed.hostname.lower()
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid snippet")
    return value.strip() or None


_SPEC = ClientSearchSpec(_PROVIDER_ID, "web", _invoke, _project)

__all__ = ["ScrapingDogClientProtocol", "ScrapingDogSearchProvider"]
