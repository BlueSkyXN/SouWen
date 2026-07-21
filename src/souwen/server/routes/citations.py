"""OpenCitations enrichment routes (not keyword paper search)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from souwen.core.exceptions import NotFoundError, ParseError, RateLimitError, SourceUnavailableError
from souwen.editions import EditionError
from souwen.server.auth import check_search_auth
from souwen.server.limiter import rate_limit_search
from souwen.server.routes._common import logger, normalize_required_query_arg
from souwen.server.schemas import CitationCountResponse, CitationGraphResponse

router = APIRouter(prefix="/citations")


async def _run(coro, *, identifier: str, timeout: float | None):
    try:
        return await asyncio.wait_for(coro, timeout=timeout) if timeout is not None else await coro
    except asyncio.TimeoutError as exc:
        logger.warning("citation enrichment timeout: identifier=%s", identifier)
        raise HTTPException(status_code=504, detail="citation enrichment 超时") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EditionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (SourceUnavailableError, ParseError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - public route must not leak provider internals.
        logger.warning("citation enrichment failed: identifier=%s", identifier, exc_info=True)
        raise HTTPException(status_code=502, detail="citation enrichment 不可用") from exc


@router.get(
    "/count",
    response_model=CitationCountResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_citation_count(
    identifier: str = Query(..., min_length=1, max_length=500),
    timeout: float | None = Query(None, ge=1, le=120),
):
    """Return the OpenCitations incoming-citation count for one DOI/PMID/OMID."""
    from souwen.citations import get_citation_count

    identifier = normalize_required_query_arg(identifier, "identifier")
    return await _run(get_citation_count(identifier), identifier=identifier, timeout=timeout)


@router.get(
    "/incoming",
    response_model=CitationGraphResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_citation_incoming(
    identifier: str = Query(..., min_length=1, max_length=500),
    max_edges: int = Query(
        100, ge=1, le=1000, description="SouWen local output cap; not upstream pagination"
    ),
    timeout: float | None = Query(None, ge=1, le=120),
):
    """Return incoming citation edges; ``max_edges`` is a local response cap."""
    from souwen.citations import get_incoming_citations

    identifier = normalize_required_query_arg(identifier, "identifier")
    return await _run(
        get_incoming_citations(identifier, max_edges=max_edges),
        identifier=identifier,
        timeout=timeout,
    )


@router.get(
    "/references",
    response_model=CitationGraphResponse,
    dependencies=[Depends(rate_limit_search), Depends(check_search_auth)],
)
async def api_citation_references(
    identifier: str = Query(..., min_length=1, max_length=500),
    max_edges: int = Query(
        100, ge=1, le=1000, description="SouWen local output cap; not upstream pagination"
    ),
    timeout: float | None = Query(None, ge=1, le=120),
):
    """Return outgoing reference edges; ``max_edges`` is a local response cap."""
    from souwen.citations import get_references

    identifier = normalize_required_query_arg(identifier, "identifier")
    return await _run(
        get_references(identifier, max_edges=max_edges), identifier=identifier, timeout=timeout
    )
