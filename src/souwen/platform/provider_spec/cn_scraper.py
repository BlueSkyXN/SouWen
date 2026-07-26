"""Strict Provider v2 projection for anonymous Chinese/social web scrapers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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

from .factory import ClientSearchProvider, ClientSearchSpec


@dataclass(frozen=True, slots=True)
class CnScraperBinding:
    """Reviewed fixed behavior of one existing anonymous web-search client."""

    provider_id: str
    domain: str
    max_limit: int = 100
    result_host: str | None = None


class CnScraperSearchProvider(ClientSearchProvider):
    """Search-only bridge for normalized ``WebSearchResponse`` clients."""

    def __init__(self, client: Any, binding: CnScraperBinding, *, enabled: bool = True) -> None:
        self.binding = binding
        super().__init__(client, cn_scraper_search_spec(binding), enabled=enabled)


def cn_scraper_search_spec(binding: CnScraperBinding) -> ClientSearchSpec:
    """Build a first-page-only bridge with an explicit existing result bound."""

    async def invoke(client: Any, request: SearchRequest, limit: int) -> Any:
        if limit > binding.max_limit:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=binding.provider_id)
        return await client.search(request.query, max_results=limit)

    def project(response: Any, limit: int, context: RequestContext) -> SearchPage:
        return project_cn_scraper_search_page(binding, response, limit, context)

    return ClientSearchSpec(binding.provider_id, binding.domain, invoke, project)


def project_cn_scraper_search_page(
    binding: CnScraperBinding,
    response: Any,
    limit: int,
    context: RequestContext,
) -> SearchPage:
    """Project only title, URL and snippet; existing ``raw`` never crosses the boundary."""

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= binding.max_limit:
        raise ValueError("invalid canonical search limit")
    if getattr(response, "source", None) != binding.provider_id:
        raise ValueError("unexpected existing web search response source")
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    if (
        getattr(response, "page", None) != 1
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or (
            total is not None
            and (not isinstance(total, int) or isinstance(total, bool) or total < len(results))
        )
    ):
        raise ValueError("invalid existing web search response")
    return SearchPage(
        items=tuple(_item(binding, result, rank) for rank, result in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=(binding.provider_id,), succeeded=(binding.provider_id,)),
        context=context,
    )


def _item(binding: CnScraperBinding, result: Any, rank: int) -> SearchItem:
    if getattr(result, "source", None) != binding.provider_id:
        raise ValueError("unexpected existing web result source")
    title = _text(getattr(result, "title", None), "title", maximum=2048)
    url = _url(getattr(result, "url", None), binding.result_host)
    identifier = sha256(url.encode("utf-8")).hexdigest()
    return SearchItem(
        id=f"{binding.provider_id}:{identifier}",
        title=title,
        url=url,
        snippet=_optional_text(getattr(result, "snippet", None), maximum=20_000),
        rank=rank,
        provenance=(Provenance(provider=binding.provider_id, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            identifiers=(SearchIdentifier(scheme=binding.provider_id, value=identifier),)
        ),
    )


def _url(value: Any, result_host: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing record URL")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("invalid record URL")
    hostname = parsed.hostname.lower()
    if (
        result_host is not None
        and hostname != result_host
        and not hostname.endswith(f".{result_host}")
    ):
        raise ValueError("record URL is outside the reviewed result domain")
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _text(value: Any, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()) or len(normalized) > maximum:
        raise ValueError(f"invalid {field}")
    return normalized


def _optional_text(value: Any, *, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid snippet")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError("snippet exceeds canonical limit")
    return normalized or None


__all__ = [
    "CnScraperBinding",
    "CnScraperSearchProvider",
    "cn_scraper_search_spec",
    "project_cn_scraper_search_page",
]
