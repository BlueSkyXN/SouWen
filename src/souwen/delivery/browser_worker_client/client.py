"""Fail-closed API-runtime client for the loopback Browser Fetch Worker."""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from souwen.common_runtime.security import ResolvedFetchTarget, resolve_fetch_target_async
from souwen.platform.provider_spi import (
    ContentMetadata,
    ExecutionContext,
    FetchResult,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    RequestContext,
)
from souwen.worker.browser_fetch.protocol import (
    BROWSER_WORKER_CONTRACT_MAJOR,
    WorkerErrorResponse,
    WorkerFetchRequest,
    WorkerFetchResponse,
    WorkerProbeResponse,
)


ResolveTarget = Callable[[str], Awaitable[tuple[ResolvedFetchTarget | None, str]]]


def _validate_base_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Browser Worker URL must be loopback HTTP on 127.0.0.1")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Browser Worker URL port is invalid") from None
    if port is None or not 1 <= port <= 65535:
        raise ValueError("Browser Worker URL requires an explicit valid port")
    return f"http://127.0.0.1:{port}"


class BrowserWorkerClient:
    """Browser execution mode for Fetch; not a discoverable business Provider."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        resolver: ResolveTarget = resolve_fetch_target_async,
        client: httpx.AsyncClient | None = None,
        expected_source_sha: str | None = None,
        expected_config_revision: str | None = None,
        expected_runtime_version: str | None = None,
        expected_inventory_digest: str | None = None,
    ) -> None:
        if len(token) < 32:
            raise ValueError("Browser Worker token must contain at least 32 characters")
        self._base_url = _validate_base_url(base_url)
        self._token = token
        self._resolver = resolver
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            trust_env=False,
            follow_redirects=False,
        )
        self._owns_client = client is None
        self._expected_source_sha = expected_source_sha
        self._expected_config_revision = expected_config_revision
        self._expected_runtime_version = expected_runtime_version
        self._expected_inventory_digest = expected_inventory_digest

    def _headers(self, request_id: str, remaining_seconds: float) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-SouWen-Contract-Major": str(BROWSER_WORKER_CONTRACT_MAJOR),
            "X-Request-ID": request_id,
            "X-SouWen-Deadline-Ms": str(int((time.time() + remaining_seconds) * 1000)),
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        request_id: str,
        execution: ExecutionContext,
        json_body: dict[str, object] | None = None,
    ) -> httpx.Response:
        execution.raise_if_cancelled_or_expired()
        remaining = execution.remaining_seconds
        request_task = asyncio.create_task(
            self._client.request(
                method,
                path,
                headers=self._headers(request_id, remaining),
                json=json_body,
                timeout=remaining,
            )
        )
        cancel_task = asyncio.create_task(execution.cancel_event.wait())
        try:
            done, _pending = await asyncio.wait(
                {request_task, cancel_task},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_task in done and execution.cancelled:
                request_task.cancel()
                await asyncio.gather(request_task, return_exceptions=True)
                raise ProviderError(ProviderErrorCode.CANCELLED)
            if request_task not in done:
                request_task.cancel()
                await asyncio.gather(request_task, return_exceptions=True)
                raise ProviderError(ProviderErrorCode.WORKER_TIMEOUT)
            return await request_task
        except ProviderError:
            raise
        except (httpx.TimeoutException, TimeoutError):
            raise ProviderError(ProviderErrorCode.WORKER_TIMEOUT) from None
        except httpx.HTTPError:
            raise ProviderError(ProviderErrorCode.WORKER_UNAVAILABLE) from None
        finally:
            cancel_task.cancel()
            await asyncio.gather(cancel_task, return_exceptions=True)

    def _validate_evidence(self, evidence) -> None:
        if evidence.contract_major != BROWSER_WORKER_CONTRACT_MAJOR:
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH)
        if (
            self._expected_source_sha is not None
            and evidence.source_sha != self._expected_source_sha
        ):
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH)
        if (
            self._expected_config_revision is not None
            and evidence.config_revision != self._expected_config_revision
        ):
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH)
        if (
            self._expected_runtime_version is not None
            and evidence.runtime_version != self._expected_runtime_version
        ):
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH)
        if (
            self._expected_inventory_digest is not None
            and evidence.provider_inventory_digest != self._expected_inventory_digest
        ):
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH)

    def _raise_worker_error(self, response: httpx.Response, request_id: str) -> None:
        try:
            receipt = WorkerErrorResponse.model_validate(response.json())
        except Exception:
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH) from None
        mapping = {
            "worker_unauthorized": ProviderErrorCode.INVALID_CONFIG,
            "worker_invalid_request": ProviderErrorCode.INVALID_REQUEST,
            "worker_protocol_mismatch": ProviderErrorCode.WORKER_PROTOCOL_MISMATCH,
            "worker_overloaded": ProviderErrorCode.WORKER_OVERLOADED,
            "worker_timeout": ProviderErrorCode.WORKER_TIMEOUT,
            "worker_unavailable": ProviderErrorCode.WORKER_UNAVAILABLE,
            "worker_not_ready": ProviderErrorCode.WORKER_NOT_READY,
            "policy_blocked": ProviderErrorCode.POLICY_BLOCKED,
            "empty_content": ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
        }
        expected_status = {
            "worker_unauthorized": 401,
            "worker_invalid_request": 400,
            "worker_protocol_mismatch": 409,
            "worker_overloaded": 429,
            "worker_timeout": 504,
            "worker_unavailable": 502,
            "worker_not_ready": 503,
            "policy_blocked": 403,
            "empty_content": 502,
        }
        if (
            receipt.error.request_id != request_id
            or response.status_code != expected_status[receipt.error.code]
        ):
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH)
        raise ProviderError(
            mapping[receipt.error.code],
            provider_id="builtin-fetch",
        )

    async def fetch(
        self,
        request: FetchTargetRequest,
        request_context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchResult:
        if request.policy is not None and request.policy.respect_robots is True:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)
        target_url = str(request.target)
        resolved, _reason = await self._resolver(target_url)
        if resolved is None:
            raise ProviderError(ProviderErrorCode.POLICY_BLOCKED, provider_id="builtin-fetch")
        max_code_points = (
            request.content.max_code_points
            if request.content is not None and request.content.max_code_points is not None
            else 200_000
        )
        payload = WorkerFetchRequest(
            target=request.target,
            max_code_points=max_code_points,
        )
        response = await self._request(
            "POST",
            "/internal/v1/fetch",
            request_id=request_context.request_id,
            execution=execution,
            json_body=payload.model_dump(mode="json"),
        )
        if response.status_code != 200:
            self._raise_worker_error(response, request_context.request_id)
        try:
            receipt = WorkerFetchResponse.model_validate(response.json())
        except Exception:
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH) from None
        if receipt.request_id != request_context.request_id:
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH)
        self._validate_evidence(receipt.evidence)
        item = receipt.item
        return FetchResult(
            target=request.target,
            final_url=item.final_url,
            status="success",
            title=item.title,
            content=item.content,
            content_metadata=ContentMetadata(
                media_type=item.media_type,
                charset=item.charset,
                retrieved_at=item.retrieved_at,
                truncated=item.truncated,
                content_length=item.content_length,
                quality=item.quality,
            ),
            provenance=(
                Provenance(
                    provider="builtin-fetch",
                    attempt=2,
                    outcome="success",
                    retrieved_at=item.retrieved_at,
                ),
            ),
        )

    async def readiness(
        self,
        request_context: RequestContext,
        execution: ExecutionContext,
    ) -> WorkerProbeResponse:
        response = await self._request(
            "GET",
            "/internal/v1/readiness",
            request_id=request_context.request_id,
            execution=execution,
        )
        if response.status_code != 200:
            self._raise_worker_error(response, request_context.request_id)
        try:
            receipt = WorkerProbeResponse.model_validate(response.json())
        except Exception:
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH) from None
        if receipt.request_id != request_context.request_id or not receipt.ready:
            raise ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH)
        self._validate_evidence(receipt.evidence)
        return receipt

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = ["BrowserWorkerClient"]
