"""API-side loopback client, provenance, and double-policy tests."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from souwen.common_runtime.security import ResolvedFetchTarget
from souwen.delivery.browser_worker_client import BrowserWorkerClient
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
)
from souwen.worker.browser_fetch import WorkerRuntimeEvidence
from souwen.worker.browser_fetch.app import create_browser_worker_app
from souwen.worker.browser_fetch.protocol import WorkerFetchItem


TOKEN = "w" * 48


async def _allowed_resolver(url: str):
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

    def __init__(self) -> None:
        self.calls = []

    async def initialize(self):
        return None

    async def execute(self, request, *, timeout_seconds):
        self.calls.append(request)
        content = "rendered client integration content " * 3
        return WorkerFetchItem(
            final_url=request.target,
            content=content,
            media_type="text/html",
            retrieved_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
            truncated=False,
            content_length=len(content.encode()),
            quality="high",
        )

    async def close(self):
        return None


def _evidence(source_sha: str = "a" * 40) -> WorkerRuntimeEvidence:
    return WorkerRuntimeEvidence(
        source_sha=source_sha,
        runtime_version="2.0.0rc2",
        config_revision="config-r1",
        provider_inventory_digest="b" * 64,
    )


@pytest.mark.asyncio
async def test_client_executes_authenticated_loopback_and_maps_canonical_result() -> None:
    executor = _Executor()
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=executor,
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as http:
        client = BrowserWorkerClient(
            base_url="http://127.0.0.1:49266",
            token=TOKEN,
            resolver=_allowed_resolver,
            client=http,
            expected_source_sha="a" * 40,
            expected_config_revision="config-r1",
            expected_runtime_version="2.0.0rc2",
            expected_inventory_digest="b" * 64,
        )
        result = await client.fetch(
            FetchTargetRequest(target="https://example.com/page"),
            RequestContext(request_id="browser-client"),
            ExecutionContext.with_timeout(5),
        )

    assert result.status == "success"
    assert result.content_metadata.media_type == "text/html"
    assert result.provenance[0].provider == "builtin-fetch"
    assert result.provenance[0].attempt == 2
    assert executor.calls[0].model_dump().keys() == {
        "execution_mode",
        "provider",
        "target",
        "max_code_points",
    }


@pytest.mark.asyncio
async def test_client_blocks_target_before_worker_dispatch() -> None:
    async def blocked_resolver(_url: str):
        return None, "private"

    executor = _Executor()
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(),
        executor=executor,
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as http:
        client = BrowserWorkerClient(
            base_url="http://127.0.0.1:49266",
            token=TOKEN,
            resolver=blocked_resolver,
            client=http,
        )
        with pytest.raises(ProviderError) as caught:
            await client.fetch(
                FetchTargetRequest(target="http://127.0.0.1/private"),
                RequestContext(request_id="browser-client"),
                ExecutionContext.with_timeout(5),
            )

    assert caught.value.code is ProviderErrorCode.POLICY_BLOCKED
    assert executor.calls == []


@pytest.mark.asyncio
async def test_client_fails_closed_on_worker_source_mismatch() -> None:
    app = create_browser_worker_app(
        token=TOKEN,
        evidence=_evidence(source_sha="c" * 40),
        executor=_Executor(),
        initialize_executor=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as http:
        client = BrowserWorkerClient(
            base_url="http://127.0.0.1:49266",
            token=TOKEN,
            resolver=_allowed_resolver,
            client=http,
            expected_source_sha="a" * 40,
        )
        with pytest.raises(ProviderError) as caught:
            await client.fetch(
                FetchTargetRequest(target="https://example.com/page"),
                RequestContext(request_id="browser-client"),
                ExecutionContext.with_timeout(5),
            )

    assert caught.value.code is ProviderErrorCode.WORKER_PROTOCOL_MISMATCH


@pytest.mark.parametrize(
    "base_url",
    [
        "http://0.0.0.0:49266",
        "http://localhost:49266",
        "https://127.0.0.1:49266",
        "http://127.0.0.1:49266/internal",
    ],
)
def test_client_rejects_non_exact_loopback_worker_urls(base_url: str) -> None:
    with pytest.raises(ValueError):
        BrowserWorkerClient(base_url=base_url, token=TOKEN)


@pytest.mark.asyncio
async def test_client_rejects_mismatched_error_request_id() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "contract_major": 1,
                "error": {
                    "code": "worker_not_ready",
                    "message": "Worker is not ready",
                    "retryable": True,
                    "request_id": "different-request",
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:49266") as http:
        client = BrowserWorkerClient(
            base_url="http://127.0.0.1:49266",
            token=TOKEN,
            resolver=_allowed_resolver,
            client=http,
        )
        with pytest.raises(ProviderError) as caught:
            await client.readiness(
                RequestContext(request_id="expected-request"),
                ExecutionContext.with_timeout(5),
            )

    assert caught.value.code is ProviderErrorCode.WORKER_PROTOCOL_MISMATCH
