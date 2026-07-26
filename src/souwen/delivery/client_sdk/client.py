"""Thin sync and async transports over generated target operations and DTOs."""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import Mapping
from types import TracebackType
from typing import Literal, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from . import _generated_operations as operations
from ._generated_models import (
    ErrorResponse,
    FetchBatch,
    FetchRequest,
    LLMSearchRequest,
    LLMSearchResult,
    ProbeResponse,
    ProviderCatalog,
    SearchPage,
    SearchRequest,
)
from .errors import (
    ApiMajorMismatchError,
    ContractViolationError,
    SouWenAPIError,
    SouWenTransportError,
)


ResponseT = TypeVar("ResponseT", bound=BaseModel)
AuthChannel = Literal["authorization", "x-souwen-token"]
TimeoutValue = float | httpx.Timeout | None
DEFAULT_TIMEOUT_SECONDS = 125.0
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_RESERVED_HEADERS = frozenset(
    {"authorization", "x-souwen-token", "x-souwen-api-major", "x-request-id"}
)
_RATE_LIMIT_HEADERS = (
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
)


def _normalize_base_url(value: str) -> str:
    try:
        url = httpx.URL(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("base_url must be a valid HTTP(S) URL") from exc
    if url.scheme not in {"http", "https"} or not url.host:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("base_url cannot contain userinfo, query, or fragment")
    return str(url).rstrip("/")


def _validate_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    normalized = dict(headers or {})
    conflicts = sorted(name for name in normalized if name.lower() in _RESERVED_HEADERS)
    if conflicts:
        raise ValueError(f"reserved SDK headers cannot be overridden: {', '.join(conflicts)}")
    return normalized


def _validate_request_id(value: str | None) -> str:
    request_id = value or uuid4().hex
    if not _REQUEST_ID.fullmatch(request_id):
        raise ValueError("request_id must match [A-Za-z0-9_-]{1,64}")
    return request_id


def _auth_headers(
    token: str | None,
    auth_channel: AuthChannel,
    edge_token: str | None,
) -> dict[str, str]:
    if auth_channel not in {"authorization", "x-souwen-token"}:
        raise ValueError("auth_channel must be 'authorization' or 'x-souwen-token'")
    if token == "" or edge_token == "":
        raise ValueError("token values cannot be empty")
    if edge_token is not None and token is not None and auth_channel == "authorization":
        raise ValueError(
            "edge_token occupies Authorization; use auth_channel='x-souwen-token' "
            "for the application token"
        )
    headers: dict[str, str] = {}
    if edge_token is not None:
        headers["Authorization"] = f"Bearer {edge_token}"
    if token is not None:
        name = "Authorization" if auth_channel == "authorization" else "X-SouWen-Token"
        headers[name] = f"Bearer {token}" if name == "Authorization" else token
    return headers


def _request_headers(
    base_headers: Mapping[str, str],
    auth_headers: Mapping[str, str],
    request_id: str,
) -> dict[str, str]:
    return {
        **base_headers,
        **auth_headers,
        "Accept": "application/json",
        "X-SouWen-API-Major": str(operations.SUPPORTED_API_MAJOR),
        "X-Request-ID": request_id,
    }


def _verify_contract_headers(response: httpx.Response) -> str:
    received_major = response.headers.get("X-SouWen-API-Major")
    if received_major != str(operations.SUPPORTED_API_MAJOR):
        raise ApiMajorMismatchError(operations.SUPPORTED_API_MAJOR, received_major)
    rollout = response.headers.get("X-SouWen-Rollout-Mode")
    if rollout != "target":
        raise ContractViolationError(
            f"target SDK received invalid X-SouWen-Rollout-Mode {rollout!r}"
        )
    request_id = response.headers.get("X-Request-ID")
    if request_id is None or not _REQUEST_ID.fullmatch(request_id):
        raise ContractViolationError("response is missing a valid X-Request-ID")
    return request_id


def _response_json(response: httpx.Response) -> object:
    try:
        return response.json()
    except (ValueError, UnicodeError) as exc:
        raise ContractViolationError("response body is not canonical JSON") from exc


def _check_context(payload: BaseModel, request_id: str) -> None:
    context = getattr(payload, "context", None)
    if context is None or getattr(context, "request_id", None) != request_id:
        raise ContractViolationError("response context does not match X-Request-ID")
    if getattr(context, "api_major", None) != operations.SUPPORTED_API_MAJOR:
        raise ContractViolationError("response context carries the wrong API major")
    if isinstance(payload, ErrorResponse) and payload.error.request_id != request_id:
        raise ContractViolationError("error request_id does not match X-Request-ID")
    if isinstance(payload, ProbeResponse) and payload.rollout_mode != "target":
        raise ContractViolationError("probe payload does not identify target rollout")


def _decode_response(
    response: httpx.Response,
    model: type[ResponseT],
    response_statuses: tuple[int, ...],
) -> ResponseT:
    request_id = _verify_contract_headers(response)
    data = _response_json(response)
    if response.status_code not in response_statuses:
        try:
            error = ErrorResponse.model_validate(data)
        except ValidationError as exc:
            raise ContractViolationError(
                "non-success response is not canonical ErrorResponse"
            ) from exc
        _check_context(error, request_id)
        rate_limit = {
            name: value
            for name in _RATE_LIMIT_HEADERS
            if (value := response.headers.get(name)) is not None
        }
        raise SouWenAPIError(
            response.status_code,
            error,
            retry_after=response.headers.get("Retry-After"),
            rate_limit=rate_limit,
        )
    try:
        payload = model.model_validate(data)
    except ValidationError as exc:
        raise ContractViolationError(
            f"success response does not match generated {model.__name__}"
        ) from exc
    _check_context(payload, request_id)
    return payload


def _payload_json(payload: BaseModel | None) -> dict | None:
    return payload.model_dump(mode="json", exclude_none=True) if payload is not None else None


class SouWenClient:
    """Synchronous target REST client generated against API major 2."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        auth_channel: AuthChannel = "authorization",
        edge_token: str | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT_SECONDS,
        headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if transport is not None and http_client is not None:
            raise ValueError("transport and http_client are mutually exclusive")
        self._base_url = _normalize_base_url(base_url)
        self._headers = _validate_headers(headers)
        self._auth_headers = _auth_headers(token, auth_channel, edge_token)
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        if any(name.lower() in _RESERVED_HEADERS for name in self._client.headers):
            raise ValueError("injected http_client cannot preconfigure reserved SDK headers")
        self._compatibility_verified = False
        self._preflight_lock = threading.Lock()

    def _send(
        self,
        operation: operations.Operation,
        response_model: type[ResponseT],
        *,
        payload: BaseModel | None = None,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ResponseT:
        effective_request_id = _validate_request_id(request_id)
        request_kwargs: dict[str, object] = {
            "headers": _request_headers(
                self._headers,
                self._auth_headers,
                effective_request_id,
            ),
            "json": _payload_json(payload),
        }
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        try:
            response = self._client.request(
                operation.method,
                f"{self._base_url}{operation.path}",
                **request_kwargs,
            )
        except httpx.RequestError as exc:
            raise SouWenTransportError("SouWen HTTP request failed") from exc
        return _decode_response(response, response_model, operation.response_statuses)

    def preflight(self, *, timeout: TimeoutValue = None) -> ProbeResponse:
        with self._preflight_lock:
            if self._compatibility_verified:
                return self._send(operations.HEALTHZ, ProbeResponse, timeout=timeout)
            response = self._send(operations.HEALTHZ, ProbeResponse, timeout=timeout)
            self._compatibility_verified = True
            return response

    def _ensure_compatible(self, timeout: TimeoutValue) -> None:
        if not self._compatibility_verified:
            self.preflight(timeout=timeout)

    def search(
        self,
        payload: SearchRequest,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> SearchPage:
        self._ensure_compatible(timeout)
        return self._send(
            operations.SEARCH,
            SearchPage,
            payload=payload,
            request_id=request_id,
            timeout=timeout,
        )

    def llm_search(
        self,
        payload: LLMSearchRequest,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> LLMSearchResult:
        self._ensure_compatible(timeout)
        return self._send(
            operations.LLM_SEARCH,
            LLMSearchResult,
            payload=payload,
            request_id=request_id,
            timeout=timeout,
        )

    def fetch(
        self,
        payload: FetchRequest,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> FetchBatch:
        self._ensure_compatible(timeout)
        return self._send(
            operations.FETCH,
            FetchBatch,
            payload=payload,
            request_id=request_id,
            timeout=timeout,
        )

    def list_providers(
        self,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ProviderCatalog:
        self._ensure_compatible(timeout)
        return self._send(
            operations.LIST_PROVIDERS,
            ProviderCatalog,
            request_id=request_id,
            timeout=timeout,
        )

    def health(
        self, *, request_id: str | None = None, timeout: TimeoutValue = None
    ) -> ProbeResponse:
        return self._send(
            operations.HEALTH_LEGACY_ALIAS,
            ProbeResponse,
            request_id=request_id,
            timeout=timeout,
        )

    def healthz(
        self, *, request_id: str | None = None, timeout: TimeoutValue = None
    ) -> ProbeResponse:
        response = self._send(
            operations.HEALTHZ,
            ProbeResponse,
            request_id=request_id,
            timeout=timeout,
        )
        self._compatibility_verified = True
        return response

    def readiness(
        self,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ProbeResponse:
        return self._send(
            operations.READINESS_LEGACY_ALIAS,
            ProbeResponse,
            request_id=request_id,
            timeout=timeout,
        )

    def readyz(
        self, *, request_id: str | None = None, timeout: TimeoutValue = None
    ) -> ProbeResponse:
        return self._send(
            operations.READYZ,
            ProbeResponse,
            request_id=request_id,
            timeout=timeout,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SouWenClient:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()


class AsyncSouWenClient:
    """Asynchronous target REST client generated against API major 2."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        auth_channel: AuthChannel = "authorization",
        edge_token: str | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT_SECONDS,
        headers: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if transport is not None and http_client is not None:
            raise ValueError("transport and http_client are mutually exclusive")
        self._base_url = _normalize_base_url(base_url)
        self._headers = _validate_headers(headers)
        self._auth_headers = _auth_headers(token, auth_channel, edge_token)
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )
        if any(name.lower() in _RESERVED_HEADERS for name in self._client.headers):
            raise ValueError("injected http_client cannot preconfigure reserved SDK headers")
        self._compatibility_verified = False
        self._preflight_lock = asyncio.Lock()

    async def _send(
        self,
        operation: operations.Operation,
        response_model: type[ResponseT],
        *,
        payload: BaseModel | None = None,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ResponseT:
        effective_request_id = _validate_request_id(request_id)
        request_kwargs: dict[str, object] = {
            "headers": _request_headers(
                self._headers,
                self._auth_headers,
                effective_request_id,
            ),
            "json": _payload_json(payload),
        }
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        try:
            response = await self._client.request(
                operation.method,
                f"{self._base_url}{operation.path}",
                **request_kwargs,
            )
        except httpx.RequestError as exc:
            raise SouWenTransportError("SouWen HTTP request failed") from exc
        return _decode_response(response, response_model, operation.response_statuses)

    async def preflight(self, *, timeout: TimeoutValue = None) -> ProbeResponse:
        async with self._preflight_lock:
            if self._compatibility_verified:
                return await self._send(operations.HEALTHZ, ProbeResponse, timeout=timeout)
            response = await self._send(operations.HEALTHZ, ProbeResponse, timeout=timeout)
            self._compatibility_verified = True
            return response

    async def _ensure_compatible(self, timeout: TimeoutValue) -> None:
        if not self._compatibility_verified:
            await self.preflight(timeout=timeout)

    async def search(
        self,
        payload: SearchRequest,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> SearchPage:
        await self._ensure_compatible(timeout)
        return await self._send(
            operations.SEARCH,
            SearchPage,
            payload=payload,
            request_id=request_id,
            timeout=timeout,
        )

    async def llm_search(
        self,
        payload: LLMSearchRequest,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> LLMSearchResult:
        await self._ensure_compatible(timeout)
        return await self._send(
            operations.LLM_SEARCH,
            LLMSearchResult,
            payload=payload,
            request_id=request_id,
            timeout=timeout,
        )

    async def fetch(
        self,
        payload: FetchRequest,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> FetchBatch:
        await self._ensure_compatible(timeout)
        return await self._send(
            operations.FETCH,
            FetchBatch,
            payload=payload,
            request_id=request_id,
            timeout=timeout,
        )

    async def list_providers(
        self,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ProviderCatalog:
        await self._ensure_compatible(timeout)
        return await self._send(
            operations.LIST_PROVIDERS,
            ProviderCatalog,
            request_id=request_id,
            timeout=timeout,
        )

    async def health(
        self,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ProbeResponse:
        return await self._send(
            operations.HEALTH_LEGACY_ALIAS,
            ProbeResponse,
            request_id=request_id,
            timeout=timeout,
        )

    async def healthz(
        self,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ProbeResponse:
        response = await self._send(
            operations.HEALTHZ,
            ProbeResponse,
            request_id=request_id,
            timeout=timeout,
        )
        self._compatibility_verified = True
        return response

    async def readiness(
        self,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ProbeResponse:
        return await self._send(
            operations.READINESS_LEGACY_ALIAS,
            ProbeResponse,
            request_id=request_id,
            timeout=timeout,
        )

    async def readyz(
        self,
        *,
        request_id: str | None = None,
        timeout: TimeoutValue = None,
    ) -> ProbeResponse:
        return await self._send(
            operations.READYZ,
            ProbeResponse,
            request_id=request_id,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncSouWenClient:
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


__all__ = ["AsyncSouWenClient", "SouWenClient"]
