"""Shared Provider v2 bridge for normalized research-output search clients.

The target Search contract intentionally carries only the small canonical
projection below.  Repository-specific rights, resource links, related IDs,
funding and raw payloads remain outside this Search surface.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
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

_IDENTIFIER_SCHEME = re.compile(r"^[a-z][a-z0-9_.-]{0,31}$")
_OPEN_ACCESS_STATUSES = frozenset({"open_access", "public_domain"})


class ResearchOutputSearchProvider(LegacySearchProvider):
    """Map one fixed first-page research-output client into canonical Search."""

    capability = "search"

    def __init__(
        self,
        client: Any,
        *,
        provider_id: str,
        limit_keyword: str,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            client,
            research_output_search_spec(provider_id=provider_id, limit_keyword=limit_keyword),
            enabled=enabled,
        )


def research_output_search_spec(*, provider_id: str, limit_keyword: str) -> LegacySearchSpec:
    """Build a first-page-only bridge without invoking source detail endpoints."""

    async def invoke(client: Any, request: SearchRequest, limit: int) -> Any:
        return await client.search(request.query, **{limit_keyword: limit, "page": 1})

    def project(response: Any, limit: int, context: RequestContext) -> SearchPage:
        return project_research_output_search_page(provider_id, response, limit, context)

    return LegacySearchSpec(provider_id, "research_output", invoke, project)


def project_research_output_search_page(
    provider_id: str,
    response: Any,
    limit: int,
    context: RequestContext,
) -> SearchPage:
    """Strictly project normalized metadata without exposing rich repository payloads."""

    if getattr(response, "source", None) != provider_id:
        raise ValueError("unexpected research-output response source")
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid research-output search results")
    if len(results) > limit:
        raise ValueError("research-output result page exceeds requested limit")
    if total is not None and (
        not isinstance(total, int) or isinstance(total, bool) or total < len(results)
    ):
        raise ValueError("invalid research-output result total")
    if getattr(response, "page", None) != 1 or getattr(response, "per_page", None) != limit:
        raise ValueError("legacy research-output page does not match canonical request")

    return SearchPage(
        items=tuple(_item(provider_id, value, rank) for rank, value in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(provider_id,), succeeded=(provider_id,)),
        context=context,
    )


def _item(provider_id: str, value: Any, rank: int) -> SearchItem:
    if getattr(value, "source", None) != provider_id:
        raise ValueError("unexpected research-output item source")
    identifier = _text(getattr(value, "source_record_id", None), "source record identifier")
    if len(identifier) > 512 - len(provider_id) - 1:
        raise ValueError("research-output record identifier is too long")
    title = _text(getattr(value, "title", None), "title")
    url = _http_url(getattr(value, "source_url", None))

    return SearchItem(
        id=f"{provider_id}:{identifier}",
        title=title,
        url=url,
        rank=rank,
        provenance=(Provenance(provider=provider_id, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_safe_year(getattr(value, "publication_year", None)),
            authors=_safe_creator_names(getattr(value, "creators", ())),
            identifiers=_safe_identifiers(
                provider_id, identifier, getattr(value, "identifiers", ())
            ),
            resource_type=_safe_text(
                getattr(value, "resource_type_general", None)
                or getattr(value, "resource_type", None),
                maximum=64,
            ),
            language=_safe_language(getattr(value, "language", None)),
            open_access=_explicit_open_access(getattr(value, "access", None)),
        ),
    )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise ValueError(f"research-output {field} is missing")
    return normalized


def _http_url(value: Any) -> str:
    url = _text(value, "source URL")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("invalid research-output source URL")
    return url


def _safe_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 9999:
        return value
    return None


def _safe_creator_names(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    names: list[str] = []
    for creator in value:
        name = _safe_text(getattr(creator, "name", None))
        if name is not None and name not in names:
            names.append(name)
    return tuple(names)


def _safe_identifiers(
    provider_id: str, source_record_id: str, value: Any
) -> tuple[SearchIdentifier, ...]:
    identifiers = [SearchIdentifier(scheme=provider_id, value=source_record_id)]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return tuple(identifiers)
    seen = {(provider_id, source_record_id)}
    for item in value:
        scheme = getattr(item, "scheme", None)
        raw_value = getattr(item, "value", None)
        if not isinstance(scheme, str) or not isinstance(raw_value, str):
            continue
        normalized_scheme = scheme.strip().lower()
        normalized_value = raw_value.strip()
        if (
            not _IDENTIFIER_SCHEME.fullmatch(normalized_scheme)
            or not normalized_value
            or len(normalized_value) > 512
            or (normalized_scheme, normalized_value) in seen
        ):
            continue
        identifiers.append(SearchIdentifier(scheme=normalized_scheme, value=normalized_value))
        seen.add((normalized_scheme, normalized_value))
    return tuple(identifiers)


def _safe_text(value: Any, *, maximum: int | None = None) -> str | None:
    if not isinstance(value, str) or not (normalized := value.strip()):
        return None
    if maximum is not None and len(normalized) > maximum:
        return None
    return normalized


def _safe_language(value: Any) -> str | None:
    normalized = _safe_text(value, maximum=35)
    return normalized if normalized is not None and len(normalized) >= 2 else None


def _explicit_open_access(access: Any) -> bool | None:
    status = getattr(access, "status", None)
    return True if status in _OPEN_ACCESS_STATUSES else None


__all__ = ["ResearchOutputSearchProvider", "research_output_search_spec"]
