"""Shared Provider v2 projection for bounded legacy book-catalog searches."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from souwen.platform.provider_spec import LegacySearchProvider, LegacySearchSpec
from souwen.platform.provider_spi import (
    PageInfo,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)


class BookCatalogClientProtocol(Protocol):
    """Minimum search-only contract implemented by legacy book clients."""

    async def search(self, query: str, per_page: int = 10, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class BookCatalogBinding:
    """Fixed source behavior; callers cannot request legacy detail methods."""

    provider_id: str
    page_supported: bool
    max_limit: int = 100
    fixed_search_kwargs: tuple[tuple[str, object], ...] = ()


class BookCatalogSearchProvider(LegacySearchProvider):
    """Search-only bridge that projects ``BookResult`` into canonical ``SearchItem``."""

    def __init__(
        self,
        client: BookCatalogClientProtocol,
        binding: BookCatalogBinding,
        *,
        enabled: bool = True,
    ) -> None:
        self.binding = binding
        super().__init__(client, _legacy_spec(binding), enabled=enabled)


def _legacy_spec(binding: BookCatalogBinding) -> LegacySearchSpec:
    async def invoke(client: Any, request: SearchRequest, limit: int) -> Any:
        if limit > binding.max_limit:
            raise ProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                provider_id=binding.provider_id,
            )
        kwargs = dict(binding.fixed_search_kwargs)
        kwargs["per_page"] = limit
        if binding.page_supported:
            # Provider v2 intentionally exposes cursor-free first-page search only.
            kwargs["page"] = 1
        return await client.search(request.query, **kwargs)

    def project(response: Any, limit: int, context: RequestContext) -> SearchPage:
        return project_book_catalog_search(response, binding.provider_id, limit, context)

    return LegacySearchSpec(binding.provider_id, "book", invoke, project)


def project_book_catalog_search(
    response: Any, provider_id: str, limit: int, context: RequestContext
) -> SearchPage:
    """Validate the legacy envelope and project only canonical, safe book fields."""

    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 100
        or getattr(response, "source", None) != provider_id
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or (
            total is not None
            and (not isinstance(total, int) or isinstance(total, bool) or total < len(results))
        )
    ):
        raise ValueError("invalid legacy book search response")
    return SearchPage(
        items=tuple(
            _book_item(result, provider_id, rank) for rank, result in enumerate(results, 1)
        ),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=(provider_id,), succeeded=(provider_id,)),
        context=context,
    )


def _book_item(result: Any, provider_id: str, rank: int) -> SearchItem:
    if getattr(result, "source", None) != provider_id:
        raise ValueError("unexpected legacy book result source")
    source_record_id = _required_text(getattr(result, "source_record_id", None), "source_record_id")
    title = _required_text(getattr(result, "title", None), "title")
    url = _canonical_url(getattr(result, "source_url", None))
    identifiers = _identifiers(getattr(result, "identifiers", None))
    authors = _authors(getattr(result, "authors", None))
    year = _year(
        getattr(result, "first_publish_year", None)
        if getattr(result, "first_publish_year", None) is not None
        else getattr(result, "copyright_year", None)
    )
    language = _language(getattr(result, "languages", None))
    return SearchItem(
        id=f"{provider_id}:{source_record_id}",
        title=title,
        url=url,
        snippet=_optional_text(getattr(result, "description", None), "description"),
        rank=rank,
        provenance=(Provenance(provider=provider_id, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            authors=authors,
            identifiers=identifiers,
            resource_type="book",
            language=language,
            open_access=_open_access(getattr(result, "access", None)),
        ),
    )


def _identifiers(value: Any) -> tuple[SearchIdentifier, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("invalid book identifiers")
    identifiers: list[SearchIdentifier] = []
    for identifier in value:
        scheme = _required_text(getattr(identifier, "scheme", None), "identifier scheme").lower()
        item_value = _required_text(getattr(identifier, "value", None), "identifier value")
        identifiers.append(SearchIdentifier(scheme=scheme, value=item_value))
    return tuple(identifiers)


def _authors(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("invalid book authors")
    authors = tuple(
        _required_text(getattr(author, "name", None), "author name") for author in value
    )
    if len(authors) != len(set(authors)):
        raise ValueError("duplicate book authors")
    return authors


def _year(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid book publication year")
    return value


def _language(value: Any) -> str | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("invalid book languages")
    if not value:
        return None
    return _required_text(value[0], "language")


def _open_access(access: Any) -> bool | None:
    status = getattr(access, "status", None)
    if status in {"open_access", "public_domain"}:
        return True
    if status in {"preview", "borrow", "restricted"}:
        return False
    if status in {"metadata_only", "unknown"}:
        return None
    raise ValueError("invalid book access status")


def _canonical_url(value: Any) -> str:
    raw = _required_text(value, "source_url")
    parsed = urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("invalid book source_url")
    host = parsed.hostname.lower()
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise ValueError(f"invalid book {field}")
    return normalized


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


__all__ = [
    "BookCatalogBinding",
    "BookCatalogClientProtocol",
    "BookCatalogSearchProvider",
    "project_book_catalog_search",
]
