"""Internal FastAPI app for the authenticated loopback Browser Worker."""

from __future__ import annotations

import asyncio
import hmac
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .executor import BrowserExecutionError
from .protocol import (
    BROWSER_WORKER_CONTRACT_MAJOR,
    BROWSER_WORKER_MAX_DEADLINE_SECONDS,
    BROWSER_WORKER_PAGE_SLOTS,
    WorkerErrorCode,
    WorkerErrorDetail,
    WorkerErrorResponse,
    WorkerFetchItem,
    WorkerFetchRequest,
    WorkerFetchResponse,
    WorkerProbeResponse,
    WorkerRuntimeEvidence,
)


class BrowserExecutor(Protocol):
    @property
    def ready(self) -> bool: ...

    async def initialize(self) -> None: ...

    async def execute(
        self,
        request: WorkerFetchRequest,
        *,
        timeout_seconds: float,
    ) -> WorkerFetchItem: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class GuardContext:
    request_id: str
    remaining_seconds: float


class WorkerRequestError(RuntimeError):
    def __init__(
        self,
        code: WorkerErrorCode,
        status_code: int,
        request_id: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.request_id = request_id
        self.retryable = retryable


_SAFE_MESSAGES: dict[WorkerErrorCode, str] = {
    "worker_unauthorized": "Worker authentication failed",
    "worker_invalid_request": "Worker request is invalid",
    "worker_protocol_mismatch": "Worker contract major does not match",
    "worker_overloaded": "Worker page capacity is exhausted",
    "worker_timeout": "Worker deadline expired",
    "worker_unavailable": "Worker execution is unavailable",
    "worker_not_ready": "Worker is not ready",
    "policy_blocked": "Browser target was blocked by policy",
    "empty_content": "Browser target returned empty content",
}


class WorkerPageCapacity:
    """Zero-queue gate with exactly two active page slots."""

    def __init__(self, limit: int = BROWSER_WORKER_PAGE_SLOTS) -> None:
        if limit != BROWSER_WORKER_PAGE_SLOTS:
            raise ValueError("RC2 Browser Worker page slots are fixed at 2")
        self._limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return self._active

    @asynccontextmanager
    async def claim(self, request_id: str) -> AsyncIterator[None]:
        async with self._lock:
            if self._active >= self._limit:
                raise WorkerRequestError(
                    "worker_overloaded",
                    429,
                    request_id,
                    retryable=True,
                )
            self._active += 1
        try:
            yield
        finally:
            async with self._lock:
                self._active -= 1


def _safe_request_id(request: Request) -> str:
    value = request.headers.get("X-Request-ID", "").strip()
    return value if 1 <= len(value) <= 128 else "unknown"


def _error_response(error: WorkerRequestError) -> JSONResponse:
    payload = WorkerErrorResponse(
        error=WorkerErrorDetail(
            code=error.code,
            message=_SAFE_MESSAGES[error.code],
            retryable=error.retryable,
            request_id=error.request_id,
        )
    )
    return JSONResponse(status_code=error.status_code, content=payload.model_dump(mode="json"))


def _guard(request: Request, token: str) -> GuardContext:
    request_id = _safe_request_id(request)
    authorization = request.headers.get("Authorization", "")
    scheme, separator, supplied_token = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not supplied_token
        or not hmac.compare_digest(supplied_token, token)
    ):
        raise WorkerRequestError("worker_unauthorized", 401, request_id)

    major = request.headers.get("X-SouWen-Contract-Major")
    if major != str(BROWSER_WORKER_CONTRACT_MAJOR):
        raise WorkerRequestError("worker_protocol_mismatch", 409, request_id)

    if request_id == "unknown":
        raise WorkerRequestError("worker_invalid_request", 400, request_id)

    raw_deadline = request.headers.get("X-SouWen-Deadline-Ms", "")
    try:
        deadline_ms = int(raw_deadline)
    except (TypeError, ValueError):
        raise WorkerRequestError("worker_invalid_request", 400, request_id) from None
    remaining = deadline_ms / 1000.0 - time.time()
    if remaining <= 0:
        raise WorkerRequestError("worker_timeout", 504, request_id, retryable=True)
    if remaining > BROWSER_WORKER_MAX_DEADLINE_SECONDS:
        raise WorkerRequestError("worker_invalid_request", 400, request_id)
    return GuardContext(request_id=request_id, remaining_seconds=remaining)


def create_browser_worker_app(
    *,
    token: str,
    evidence: WorkerRuntimeEvidence,
    executor: BrowserExecutor,
    initialize_executor: bool = True,
    capacity: WorkerPageCapacity | None = None,
) -> FastAPI:
    """Create the internal-only app; network binding is validated by the runtime entry point."""
    if len(token) < 32:
        raise ValueError("Browser Worker token must contain at least 32 characters")
    page_capacity = capacity or WorkerPageCapacity()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if initialize_executor:
            try:
                await executor.initialize()
            except BrowserExecutionError:
                pass
        try:
            yield
        finally:
            await executor.close()

    app = FastAPI(
        title="SouWen Browser Fetch Worker",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def authenticate_internal_request(request: Request, call_next):
        try:
            request.state.worker_guard = _guard(request, token)
        except WorkerRequestError as exc:
            return _error_response(exc)
        return await call_next(request)

    @app.exception_handler(WorkerRequestError)
    async def handle_worker_request_error(
        _request: Request,
        exc: WorkerRequestError,
    ) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            WorkerRequestError("worker_invalid_request", 400, _safe_request_id(request))
        )

    @app.get("/internal/v1/health", response_model=WorkerProbeResponse)
    async def health(request: Request) -> WorkerProbeResponse:
        guard: GuardContext = request.state.worker_guard
        return WorkerProbeResponse(
            request_id=guard.request_id,
            status="alive",
            ready=executor.ready,
            evidence=evidence,
        )

    @app.get("/internal/v1/readiness", response_model=WorkerProbeResponse)
    async def readiness(request: Request):
        guard: GuardContext = request.state.worker_guard
        if not executor.ready:
            raise WorkerRequestError(
                "worker_not_ready",
                503,
                guard.request_id,
                retryable=True,
            )
        return WorkerProbeResponse(
            request_id=guard.request_id,
            status="ready",
            ready=True,
            evidence=evidence,
        )

    @app.post("/internal/v1/fetch", response_model=WorkerFetchResponse)
    async def fetch(payload: WorkerFetchRequest, request: Request):
        guard: GuardContext = request.state.worker_guard
        if not executor.ready:
            raise WorkerRequestError(
                "worker_not_ready",
                503,
                guard.request_id,
                retryable=True,
            )
        try:
            async with page_capacity.claim(guard.request_id):
                execution_task = asyncio.create_task(
                    executor.execute(
                        payload,
                        timeout_seconds=guard.remaining_seconds,
                    )
                )

                async def wait_for_disconnect() -> None:
                    while True:
                        message = await request.receive()
                        if message.get("type") == "http.disconnect":
                            return

                disconnect_task = asyncio.create_task(wait_for_disconnect())
                deadline_task = asyncio.create_task(asyncio.sleep(guard.remaining_seconds))
                try:
                    done, _pending = await asyncio.wait(
                        {execution_task, disconnect_task, deadline_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if execution_task not in done and (
                        disconnect_task in done or deadline_task in done
                    ):
                        execution_task.cancel()
                        await asyncio.gather(execution_task, return_exceptions=True)
                        raise BrowserExecutionError("worker_timeout", retryable=True)
                    item = await execution_task
                finally:
                    disconnect_task.cancel()
                    deadline_task.cancel()
                    await asyncio.gather(
                        disconnect_task,
                        deadline_task,
                        return_exceptions=True,
                    )
                    if not execution_task.done():
                        execution_task.cancel()
                        await asyncio.gather(execution_task, return_exceptions=True)
        except BrowserExecutionError as exc:
            status_code = {
                "policy_blocked": 403,
                "empty_content": 502,
                "worker_timeout": 504,
                "worker_not_ready": 503,
                "worker_unavailable": 502,
            }.get(exc.code, 502)
            code: WorkerErrorCode = exc.code if exc.code in _SAFE_MESSAGES else "worker_unavailable"
            raise WorkerRequestError(
                code,
                status_code,
                guard.request_id,
                retryable=exc.retryable,
            ) from None
        return WorkerFetchResponse(
            request_id=guard.request_id,
            evidence=evidence,
            item=item,
        )

    return app


__all__ = ["WorkerPageCapacity", "create_browser_worker_app"]
