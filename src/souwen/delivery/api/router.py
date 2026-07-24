"""Thin FastAPI adapters over injected Module public APIs."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from souwen.common_runtime.observability import get_request_id, get_source_sha
from souwen.modules.fetch.api import FetchBatch, FetchModule, FetchRequest
from souwen.modules.llm_search.api import LLMSearchModule, LLMSearchRequest, LLMSearchResult
from souwen.modules.search.api import SearchModule, SearchPage, SearchRequest
from souwen.platform.provider_spi import (
    ErrorResponse,
    ExecutionContext,
    ProviderError,
    RequestContext,
)

from .errors import TargetDeliveryError, from_provider_error
from .models import ProbeResponse, ProviderCatalog, ProviderCatalogItem
from .rollout import RolloutMode


Dependency = Callable[..., object]
_ERROR = {"model": ErrorResponse, "description": "Canonical target error"}


@dataclass(frozen=True, slots=True)
class ReadinessSnapshot:
    ready: bool
    components: dict[str, str]
    error: str | None = None


class ReadinessCheck(Protocol):
    def __call__(self) -> ReadinessSnapshot | Awaitable[ReadinessSnapshot]: ...


@dataclass(frozen=True, slots=True)
class RuntimeMetadata:
    version: str
    source_sha: str | None
    rollout_mode: RolloutMode
    config_revision: str | None = None


@dataclass(frozen=True, slots=True)
class TargetDeliveryServices:
    search: SearchModule
    llm_search: LLMSearchModule
    fetch: FetchModule
    provider_items: tuple[ProviderCatalogItem, ...]
    readiness: ReadinessCheck


def _context() -> RequestContext:
    return RequestContext(request_id=get_request_id())


def _require_api_major(
    api_major: str | None = Header(default=None, alias="X-SouWen-API-Major"),
) -> None:
    if api_major is not None and api_major.strip() != "2":
        raise TargetDeliveryError("api_major_mismatch", 409)


async def _readiness(check: ReadinessCheck) -> ReadinessSnapshot:
    result = check()
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, ReadinessSnapshot):
        raise RuntimeError("readiness check returned an invalid result")
    return result


def create_target_api_router(
    services: TargetDeliveryServices,
    *,
    require_user: Dependency,
    rate_limit: Dependency,
) -> APIRouter:
    router = APIRouter(
        dependencies=[Depends(require_user), Depends(rate_limit), Depends(_require_api_major)]
    )

    @router.post(
        "/search",
        response_model=SearchPage,
        operation_id="search",
        responses={code: _ERROR for code in (400, 401, 409, 429, 502, 504)},
    )
    async def search(payload: SearchRequest) -> SearchPage:
        context = _context()
        try:
            return await services.search.search(
                payload,
                context,
                ExecutionContext.with_timeout(30),
            )
        except ProviderError as exc:
            raise from_provider_error(exc) from None

    @router.post(
        "/llm-search",
        response_model=LLMSearchResult,
        operation_id="llmSearch",
        responses={code: _ERROR for code in (400, 401, 409, 429, 502, 504)},
    )
    async def llm_search(payload: LLMSearchRequest) -> LLMSearchResult:
        timeout = payload.budget.timeout_seconds if payload.budget else 90
        context = _context()
        try:
            return await services.llm_search.search(
                payload,
                context,
                ExecutionContext.with_timeout(timeout),
            )
        except ProviderError as exc:
            raise from_provider_error(exc) from None

    @router.post(
        "/fetch",
        response_model=FetchBatch,
        operation_id="fetch",
        responses={code: _ERROR for code in (400, 401, 403, 409, 413, 415, 429, 502, 503, 504)},
    )
    async def fetch(payload: FetchRequest) -> FetchBatch:
        context = _context()
        try:
            return await services.fetch.fetch(
                payload,
                context,
                ExecutionContext.with_timeout(30),
            )
        except ProviderError as exc:
            raise from_provider_error(exc) from None

    @router.get(
        "/providers",
        response_model=ProviderCatalog,
        operation_id="listProviders",
        responses={code: _ERROR for code in (400, 401, 409, 429)},
    )
    async def providers() -> ProviderCatalog:
        return ProviderCatalog(items=services.provider_items, context=_context())

    return router


def create_probe_router(
    readiness_check: ReadinessCheck,
    metadata: RuntimeMetadata,
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/health",
        response_model=ProbeResponse,
        operation_id="healthLegacyAlias",
        openapi_extra={"x-souwen-alias-of": "/healthz"},
    )
    @router.get("/healthz", response_model=ProbeResponse, operation_id="healthz")
    async def health() -> ProbeResponse:
        return ProbeResponse(
            status="ok",
            ready=True,
            version=metadata.version,
            source_sha=metadata.source_sha or get_source_sha(),
            rollout_mode=metadata.rollout_mode,
            config_revision=metadata.config_revision,
            components={"api": "ready"},
            context=_context(),
        )

    @router.get(
        "/readiness",
        response_model=ProbeResponse,
        operation_id="readinessLegacyAlias",
        responses={503: {"model": ProbeResponse, "description": "Runtime is not ready"}},
        openapi_extra={"x-souwen-alias-of": "/readyz"},
    )
    @router.get(
        "/readyz",
        response_model=ProbeResponse,
        operation_id="readyz",
        responses={503: {"model": ProbeResponse, "description": "Runtime is not ready"}},
    )
    async def readiness():
        snapshot = await _readiness(readiness_check)
        response = ProbeResponse(
            status="ready" if snapshot.ready else "not_ready",
            ready=snapshot.ready,
            version=metadata.version,
            source_sha=metadata.source_sha or get_source_sha(),
            rollout_mode=metadata.rollout_mode,
            config_revision=metadata.config_revision,
            components=snapshot.components,
            error=snapshot.error,
            context=_context(),
        )
        if snapshot.ready:
            return response
        return JSONResponse(status_code=503, content=response.model_dump(mode="json"))

    return router


__all__ = [
    "ReadinessSnapshot",
    "RuntimeMetadata",
    "TargetDeliveryServices",
    "create_probe_router",
    "create_target_api_router",
]
