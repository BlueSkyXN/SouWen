"""Provider v2 adapter that maps an injected existing OpenAlex client to canonical Search."""

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
from souwen.platform.provider_spec import ClientSearchProvider, ClientSearchSpec


_PROVIDER_ID = "openalex"


class OpenAlexClientProtocol(Protocol):
    """The minimal existing-client surface used by this target adapter."""

    async def search(
        self,
        query: str,
        filters: dict[str, str] | None = None,
        sort: str | None = None,
        page: int = 1,
        per_page: int = 10,
    ) -> Any:
        """Return a existing ``SearchResponse`` compatible object."""


class OpenAlexSearchProvider(ClientSearchProvider):
    """Search-only provider that preserves existing OpenAlex query behavior behind the SPI."""

    capability = "search"

    def __init__(self, client: OpenAlexClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _OPENALEX_BRIDGE_SPEC, enabled=enabled)


def _existing_filters(request: SearchRequest) -> dict[str, str] | None:
    """Map only canonical, reviewed filters in deterministic upstream parameter order."""
    if request.filters is None:
        return None
    filters: dict[str, str] = {}
    if request.filters.year_from is not None:
        filters["from_publication_date"] = f"{request.filters.year_from:04d}-01-01"
    if request.filters.year_to is not None:
        filters["to_publication_date"] = f"{request.filters.year_to:04d}-12-31"
    if request.filters.language is not None:
        filters["language"] = request.filters.language
    if request.filters.open_access is not None:
        filters["is_oa"] = "true" if request.filters.open_access else "false"
    if request.filters.resource_type is not None:
        filters["type"] = request.filters.resource_type
    return filters or None


def _to_search_page(response: Any, *, limit: int, context: RequestContext) -> SearchPage:
    """Strictly transform existing ``SearchResponse`` / ``PaperResult`` data to canonical DTOs."""
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing response source")
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    response_page = getattr(response, "page", None)
    response_limit = getattr(response, "per_page", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid existing search results")
    if total is not None and (not isinstance(total, int) or isinstance(total, bool) or total < 0):
        raise ValueError("invalid existing result total")
    if response_page != 1 or response_limit != limit:
        raise ValueError("existing page does not match canonical request")

    items = tuple(
        _to_search_item(paper, rank=index) for index, paper in enumerate(results, start=1)
    )
    return SearchPage(
        items=items,
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _to_search_item(paper: Any, *, rank: int) -> SearchItem:
    """Map one normalized existing paper while retaining only canonical public metadata."""
    if getattr(paper, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing paper source")
    title = _required_text(getattr(paper, "title", None))
    doi = _normalise_doi(getattr(paper, "doi", None))
    source_url = _normalise_url(getattr(paper, "source_url", None))
    if doi is None and source_url is None:
        raise ValueError("paper lacks stable identifier")

    identifiers: list[SearchIdentifier] = []
    if doi is not None:
        identifiers.append(SearchIdentifier(scheme="doi", value=doi))
    if source_url is not None:
        identifiers.append(SearchIdentifier(scheme="openalex", value=source_url))
    item_id = f"doi:{doi.lower()}" if doi is not None else f"openalex:{source_url}"
    canonical_url = f"https://doi.org/{doi}" if doi is not None else source_url
    raw = getattr(paper, "raw", {})
    if not isinstance(raw, Mapping):
        raise ValueError("invalid existing paper attributes")

    return SearchItem(
        id=item_id,
        title=title,
        url=canonical_url,
        snippet=_optional_text(getattr(paper, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_optional_int(getattr(paper, "year", None)),
            authors=_author_names(getattr(paper, "authors", None)),
            identifiers=tuple(identifiers),
            resource_type=_optional_text(raw.get("type")),
            open_access=raw.get("is_oa") if isinstance(raw.get("is_oa"), bool) else None,
            citation_count=_optional_nonnegative_int(getattr(paper, "citation_count", None)),
        ),
    )


def _required_text(value: Any) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError("missing required text")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid text")
    normalized = value.strip()
    return normalized or None


def _normalise_doi(value: Any) -> str | None:
    doi = _optional_text(value)
    if doi is None:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix) :]
            break
    doi = _required_text(doi)
    prefix, separator, suffix = doi.partition("/")
    if not separator or not prefix.startswith("10.") or not prefix[3:].isdigit() or not suffix:
        raise ValueError("invalid DOI")
    if any(character.isspace() for character in doi):
        raise ValueError("invalid DOI")
    return doi


def _normalise_url(value: Any) -> str | None:
    url = _optional_text(value)
    if url is None:
        return None
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "openalex.org"
        or not parsed.path.startswith("/W")
    ):
        raise ValueError("invalid OpenAlex source URL")
    return url


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid year")
    return value


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("invalid citation count")
    return value


def _author_names(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("invalid authors")
    names: list[str] = []
    for author in value:
        name = _required_text(getattr(author, "name", None))
        if name not in names:
            names.append(name)
    return tuple(names)


async def _bridge_invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(
        request.query, filters=_existing_filters(request), sort=None, page=1, per_page=limit
    )


def _bridge_project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    return _to_search_page(response, limit=limit, context=context)


_OPENALEX_BRIDGE_SPEC = ClientSearchSpec(
    "openalex", "paper", _bridge_invoke, _bridge_project, accepts_filters=True
)
__all__ = ["OpenAlexClientProtocol", "OpenAlexSearchProvider"]
