"""Registry-backed public citation-enrichment facade."""

from __future__ import annotations

from typing import Any

from souwen.core.exceptions import SourceUnavailableError
from souwen.models import CitationCountResponse, CitationGraphResponse
from souwen.search import search_by_capability


async def _one(
    identifier: str,
    capability: str,
    /,
    **kwargs: Any,
) -> CitationCountResponse | CitationGraphResponse:
    responses = await search_by_capability(
        identifier,
        capability,
        sources=["opencitations"],
        identifier=identifier,
        **kwargs,
    )
    if len(responses) != 1:
        raise SourceUnavailableError("OpenCitations citation enrichment 不可用")
    response = responses[0]
    if not isinstance(response, CitationCountResponse | CitationGraphResponse):
        raise SourceUnavailableError("OpenCitations 返回了非 citation enrichment 响应")
    return response


async def get_citation_count(identifier: str) -> CitationCountResponse:
    """Get the OpenCitations incoming-citation count for one work identifier."""
    response = await _one(identifier, "opencitations:citation_count")
    assert isinstance(response, CitationCountResponse)
    return response


async def get_incoming_citations(identifier: str, *, max_edges: int = 100) -> CitationGraphResponse:
    """Get incoming OpenCitations edges, with a clearly local output cap."""
    response = await _one(identifier, "opencitations:citations", max_edges=max_edges)
    assert isinstance(response, CitationGraphResponse)
    return response


async def get_references(identifier: str, *, max_edges: int = 100) -> CitationGraphResponse:
    """Get outgoing OpenCitations reference edges, with a clearly local output cap."""
    response = await _one(identifier, "opencitations:references", max_edges=max_edges)
    assert isinstance(response, CitationGraphResponse)
    return response


__all__ = ["get_citation_count", "get_incoming_citations", "get_references"]
