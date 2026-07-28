"""Deterministic authenticated Browser Worker API and capacity tests."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import httpx
import pytest

from souwen.worker.browser_fetch import WorkerRuntimeEvidence
from souwen.worker.browser_fetch.app import create_browser_worker_app
from souwen.worker.browser_fetch.executor import BrowserExecutionError
from souwen.worker.browser_fetch.protocol import WorkerFetchItem


TOKEN = "t" * 48


def _evidence(**overrides) -> WorkerRuntimeEvidence:
    values = {
        "source_sha": "a" * 40,
        "runtime_version": "2.0.0rc3",
        "config_revision": "config-r1",
        "provider_inventory_digest": "b" * 64,
    }
    values.update(overrides)
    return WorkerRuntimeEvidence(**values)


def _item(content: str = "browser rendered content " * 4) -> WorkerFetchItem:
    return WorkerFetchItem(
        final_url="https://example.com/final",
        title="Example",
        content=content,
        media_type="text/html",
        charset="utf-8",
        retrieved_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        truncated=False,
        content_length=len(content.encode()),
        quality="low" if len(content.strip()) <= 63 else "high",
    )


class _Executor:
    def __init__(self, *, ready: bool = True, error: BrowserExecutionError | None = None) -> None:
        self._ready = ready
        self.error = error
        self.calls = []
        self.closed = 0

    @property
    def ready(self) -> bool:
        return self._ready

    async def initialize(self) -> None:
        self._ready = True

    async def execute(self, request, *, timeout_seconds):
        self.calls.append((request, timeout_seconds))
        if self.error is not None:
            raise self.error
        return _item()

    async def close(self) -> None:
        self.closed += 1


def _headers(request_id: str = "worker-test", **overrides) -> dict[str, str]:
    values = {
        "Authorization": f"Bearer {TOKEN}",
        "X-SouWen-Contract-Major": "1",
        "X-Request-ID": request_id,
        "X-SouWen-Deadline-Ms": str(int((time.time() + 5) * 1000)),
    }
    values.update(overrides)
    return values


def _payload(**overrides) -> dict[str, object]:
    values: dict[str, object] = {
        "execution_mode": "playwright",
        "provider": "builtin-fetch",
        "target": "https://example.com/page",
        "max_code_points": 200000,
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_worker_requires_token_major_request_id_and_absolute_deadline() -> None:
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=_Executor(),
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as client:
        success = await client.get("/internal/v1/health", headers=_headers())
        unauthorized = await client.get("/internal/v1/health", headers={})
        mismatch = await client.get(
            "/internal/v1/health",
            headers=_headers(**{"X-SouWen-Contract-Major": "2"}),
        )
        missing_deadline_headers = _headers()
        missing_deadline_headers.pop("X-SouWen-Deadline-Ms")
        missing_deadline = await client.get(
            "/internal/v1/health",
            headers=missing_deadline_headers,
        )

    assert success.status_code == 200
    assert success.json()["evidence"]["source_sha"] == "a" * 40
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "worker_unauthorized"
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "worker_protocol_mismatch"
    assert missing_deadline.status_code == 400


@pytest.mark.asyncio
async def test_worker_rejects_bypass_fields_and_never_echoes_them() -> None:
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=_Executor(),
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as client:
        response = await client.post(
            "/internal/v1/fetch",
            headers=_headers(),
            json=_payload(skip_ssrf_check=True, cookie="private-cookie"),
        )

    serialized = response.text
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "worker_invalid_request"
    assert "private-cookie" not in serialized
    assert TOKEN not in serialized


@pytest.mark.asyncio
async def test_worker_authenticates_before_parsing_malformed_body() -> None:
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=_Executor(),
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as client:
        response = await client.post(
            "/internal/v1/fetch",
            content=b"{not-json",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "worker_unauthorized"


@pytest.mark.asyncio
async def test_worker_maps_execution_failure_without_raw_browser_detail() -> None:
    executor = _Executor(error=BrowserExecutionError("worker_unavailable", retryable=True))
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=executor,
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as client:
        response = await client.post(
            "/internal/v1/fetch",
            headers=_headers(),
            json=_payload(),
        )

    assert response.status_code == 502
    assert response.json()["error"] == {
        "code": "worker_unavailable",
        "message": "Worker execution is unavailable",
        "retryable": True,
        "request_id": "worker-test",
    }


class _BlockingExecutor(_Executor):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.two_active = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, request, *, timeout_seconds):
        self.active += 1
        if self.active == 2:
            self.two_active.set()
        try:
            await self.release.wait()
            return _item()
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_worker_has_two_page_slots_and_zero_queue_overload() -> None:
    executor = _BlockingExecutor()
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=executor,
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as client:
        first = asyncio.create_task(
            client.post("/internal/v1/fetch", headers=_headers("slot-1"), json=_payload())
        )
        second = asyncio.create_task(
            client.post("/internal/v1/fetch", headers=_headers("slot-2"), json=_payload())
        )
        await asyncio.wait_for(executor.two_active.wait(), timeout=2)
        overloaded = await client.post(
            "/internal/v1/fetch",
            headers=_headers("slot-3"),
            json=_payload(),
        )
        executor.release.set()
        first_response, second_response = await asyncio.gather(first, second)

    assert first_response.status_code == second_response.status_code == 200
    assert overloaded.status_code == 429
    assert overloaded.json()["error"]["code"] == "worker_overloaded"


class _DeadlineExecutor(_Executor):
    def __init__(self) -> None:
        super().__init__()
        self.cancelled = asyncio.Event()

    async def execute(self, request, *, timeout_seconds):
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


@pytest.mark.asyncio
async def test_absolute_deadline_cancels_execution_even_before_browser_timeout() -> None:
    executor = _DeadlineExecutor()
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=executor,
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    deadline_headers = _headers()
    deadline_headers["X-SouWen-Deadline-Ms"] = str(int((time.time() + 0.05) * 1000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as client:
        response = await client.post(
            "/internal/v1/fetch",
            headers=deadline_headers,
            json=_payload(),
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "worker_timeout"
    assert executor.cancelled.is_set()


@pytest.mark.asyncio
async def test_worker_readiness_fails_closed_when_browser_is_not_ready() -> None:
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=_Executor(ready=False),
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as client:
        health = await client.get("/internal/v1/health", headers=_headers("health"))
        readiness = await client.get("/internal/v1/readiness", headers=_headers("readiness"))

    assert health.status_code == 200
    assert health.json()["ready"] is False
    assert readiness.status_code == 503
    assert readiness.json()["error"]["code"] == "worker_not_ready"
