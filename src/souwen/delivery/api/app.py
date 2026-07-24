"""Standalone target Delivery app factory for deterministic tests and split deployment."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from souwen.common_runtime.observability import get_request_id

from .errors import TargetDeliveryError, error_response, from_http_status
from .middleware import TargetRequestContextMiddleware
from .openapi import normalize_target_openapi
from .router import (
    Dependency,
    RuntimeMetadata,
    TargetDeliveryServices,
    create_probe_router,
    create_target_api_router,
)


logger = logging.getLogger("souwen.delivery.api")
Closer = Callable[[], Awaitable[None]]


def create_target_delivery_app(
    services: TargetDeliveryServices,
    metadata: RuntimeMetadata,
    *,
    require_user: Dependency,
    rate_limit: Dependency,
    closer: Closer | None = None,
) -> FastAPI:
    """Create the target-only app without concrete Provider or config imports."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            if closer is not None:
                await closer()

    app = FastAPI(
        title="SouWen External Data API",
        version=metadata.version,
        description="Souwen v2 target External Data API",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(TargetRequestContextMiddleware, mode=metadata.rollout_mode)
    app.include_router(
        create_target_api_router(
            services,
            require_user=require_user,
            rate_limit=rate_limit,
        ),
        prefix="/api/v1",
    )
    app.include_router(create_probe_router(services.readiness, metadata))
    default_openapi = app.openapi

    def target_openapi():
        return normalize_target_openapi(default_openapi(), metadata.rollout_mode)

    app.openapi = target_openapi

    @app.exception_handler(TargetDeliveryError)
    async def target_error_handler(_request: Request, exc: TargetDeliveryError):
        return error_response(exc, get_request_id())

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException):
        return error_response(
            from_http_status(exc.status_code),
            get_request_id(),
            extra_headers=dict(exc.headers or {}),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, _exc: RequestValidationError):
        return error_response(TargetDeliveryError("invalid_request", 400), get_request_id())

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, _exc: Exception):
        request_id = get_request_id()
        logger.exception("unhandled target Delivery error [%s]", request_id)
        return error_response(TargetDeliveryError("internal_error", 500), request_id)

    return app


__all__ = ["create_target_delivery_app"]
