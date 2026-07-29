"""Real loopback HTTP server test for the Worker/client process protocol."""

from __future__ import annotations

import asyncio
import socket
import time
from datetime import datetime, timezone

import httpx
import pytest
import uvicorn

from souwen.common_runtime.security import ResolvedFetchTarget
from souwen.delivery.browser_worker_client import BrowserWorkerClient
from souwen.platform.provider_spi import ExecutionContext, FetchTargetRequest, RequestContext
from souwen.worker.browser_fetch import WorkerRuntimeEvidence
from souwen.worker.browser_fetch.app import create_browser_worker_app
from souwen.worker.browser_fetch.protocol import WorkerFetchItem


TOKEN = "l" * 48


async def _resolver(url: str):
    return (
        ResolvedFetchTarget(
            original_url=url,
            connect_url="https://1.1.1.1/page",
            host_header="example.com",
            sni_hostname="example.com",
        ),
        "",
    )


class _Executor:
    ready = True

    async def initialize(self) -> None:
        return None

    async def execute(self, request, *, timeout_seconds):
        content = "real loopback worker protocol content " * 3
        return WorkerFetchItem(
            final_url=request.target,
            content=content,
            media_type="text/html",
            retrieved_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
            truncated=False,
            content_length=len(content.encode()),
            quality="high",
        )

    async def close(self) -> None:
        return None


class _CancellationExecutor(_Executor):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def execute(self, request, *, timeout_seconds):
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


@pytest.mark.asyncio
async def test_worker_client_uses_real_authenticated_loopback_http() -> None:
    evidence = WorkerRuntimeEvidence(
        source_sha="a" * 40,
        runtime_version="2.0.0rc4",
        config_revision="config-r1",
        provider_inventory_digest="b" * 64,
    )
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=evidence,
        executor=_Executor(),
        initialize_executor=False,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    port = int(listener.getsockname()[1])
    config = uvicorn.Config(
        app,
        log_config=None,
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started is True

        client = BrowserWorkerClient(
            base_url=f"http://127.0.0.1:{port}",
            token=TOKEN,
            resolver=_resolver,
            expected_source_sha="a" * 40,
            expected_config_revision="config-r1",
        )
        try:
            result = await client.fetch(
                FetchTargetRequest(target="https://example.com/page"),
                RequestContext(request_id="real-loopback"),
                ExecutionContext.with_timeout(5),
            )
        finally:
            await client.close()
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=5)
        listener.close()

    assert result.status == "success"
    assert result.provenance[0].attempt == 2


@pytest.mark.asyncio
async def test_real_loopback_disconnect_cancels_worker_execution() -> None:
    evidence = WorkerRuntimeEvidence(
        source_sha="a" * 40,
        runtime_version="2.0.0rc4",
        config_revision="config-r1",
        provider_inventory_digest="b" * 64,
    )
    executor = _CancellationExecutor()
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=evidence,
        executor=executor,
        initialize_executor=False,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    listener.setblocking(False)
    port = int(listener.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, lifespan="on"))
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(200):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started is True
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "X-SouWen-Contract-Major": "1",
            "X-Request-ID": "disconnect-loopback",
            "X-SouWen-Deadline-Ms": str(int((time.time() + 5) * 1000)),
        }
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            request_task = asyncio.create_task(
                client.post(
                    "/internal/v1/fetch",
                    headers=headers,
                    json={
                        "execution_mode": "playwright",
                        "provider": "builtin-fetch",
                        "target": "https://example.com/page",
                        "max_code_points": 200000,
                    },
                )
            )
            await asyncio.wait_for(executor.started.wait(), timeout=2)
            request_task.cancel()
            await asyncio.gather(request_task, return_exceptions=True)
            await asyncio.wait_for(executor.cancelled.wait(), timeout=2)
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=5)
        listener.close()

    assert executor.cancelled.is_set()
