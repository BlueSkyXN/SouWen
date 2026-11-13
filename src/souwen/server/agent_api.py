"""Flat agent HTTP surface: POST /search, POST /fetch, GET /sources (SPEC 2.4).

Responses are flat JSON mirroring the compact projection: /search returns
``results[]`` and ``sources[]``; /fetch returns one bounded page with the
``next_start`` continuation token. Auth and rate limiting reuse the existing
user-credential dependencies unchanged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from souwen.agent import AgentRuntime
from souwen.modules.fetch.application.reader import DEFAULT_MAX_CHARS
from souwen.platform.provider_spi import ProviderError, ProviderErrorCode
from souwen.server.auth import check_target_user_auth
from souwen.server.limiter import rate_limit_target_data

_DOMAIN_PATTERN = r"^(web|news|paper|patent|book|code|community|wiki|images|videos)$"

_PROVIDER_ERROR_STATUS = {
    ProviderErrorCode.INVALID_REQUEST: 400,
    ProviderErrorCode.RATE_LIMITED: 429,
    ProviderErrorCode.DEADLINE_EXCEEDED: 504,
    ProviderErrorCode.POLICY_BLOCKED: 403,
}


class SearchPayload(BaseModel):
    query: str = Field(min_length=1, max_length=4096)
    domain: str = Field(default="web", pattern=_DOMAIN_PATTERN)
    limit: int = Field(default=8, ge=1, le=50)


class FetchPayload(BaseModel):
    url: str = Field(min_length=11, max_length=2048)
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=1, le=200_000)
    start: int = Field(default=0, ge=0)


def create_agent_api_router(
    runtime: AgentRuntime,
    *,
    require_user=check_target_user_auth,
    rate_limit=rate_limit_target_data,
) -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_user), Depends(rate_limit)])

    @router.post("/search", operation_id="agentSearch")
    async def search(payload: SearchPayload) -> dict[str, Any]:
        try:
            summary = await runtime.search(
                payload.query, domain=payload.domain, limit=payload.limit
            )
        except ProviderError as exc:
            raise _http_error(exc) from None
        results = [
            {
                "title": item.title,
                "url": item.url,
                "snippet": item.snippet,
                **({"year": item.year} if item.year is not None else {}),
                **({"authors": list(item.authors)} if item.authors else {}),
            }
            for item in summary.results
        ]
        return {
            "results": results,
            "sources": list(summary.sources),
            "partial": summary.partial,
        }

    @router.post("/fetch", operation_id="agentFetch")
    async def fetch(payload: FetchPayload) -> dict[str, Any]:
        try:
            page = await runtime.fetch(
                payload.url, max_chars=payload.max_chars, start=payload.start
            )
        except ProviderError as exc:
            raise _http_error(exc) from None
        return {
            "title": page.title,
            "url": page.url,
            "content": page.content,
            "total_chars": page.total_chars,
            "start": page.start,
            "next_start": page.next_start,
            "egress": page.egress,
            "sources": list(page.sources),
        }

    @router.get("/sources", operation_id="agentSources")
    async def sources() -> dict[str, Any]:
        return {
            "sources": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "domain": item.domain,
                    "availability": item.availability,
                    "reason": item.reason,
                }
                for item in runtime.sources()
            ]
        }

    return router


def _http_error(exc: ProviderError) -> HTTPException:
    status = _PROVIDER_ERROR_STATUS.get(exc.code, 502)
    detail = exc.code.value
    if exc.provider_id:
        detail = f"{exc.provider_id}: {detail}"
    return HTTPException(status_code=status, detail=detail)


__all__ = ["create_agent_api_router"]
