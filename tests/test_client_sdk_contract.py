"""Sync/async conformance for the generated target REST SDK."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from souwen.delivery.client_sdk import (
    ApiMajorMismatchError,
    AsyncSouWenClient,
    ContractViolationError,
    FetchRequest,
    LLMSearchRequest,
    ProviderRef,
    SearchPage,
    SearchRequest,
    SouWenAPIError,
    SouWenClient,
    SouWenTransportError,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _headers(request_id: str, *, major: str = "2", rollout: str = "target") -> dict[str, str]:
    return {
        "X-SouWen-API-Major": major,
        "X-SouWen-Rollout-Mode": rollout,
        "X-Request-ID": request_id,
    }


def _context(request: httpx.Request) -> dict[str, object]:
    return {
        "request_id": request.headers["X-Request-ID"],
        "api_major": 2,
        "trace_id": None,
    }


def _probe(request: httpx.Request, *, ready: bool = True) -> httpx.Response:
    request_id = request.headers["X-Request-ID"]
    path = request.url.path.removeprefix("/root")
    return httpx.Response(
        200 if ready else 503,
        headers=_headers(request_id),
        json={
            "status": (
                "ok" if path in {"/health", "/healthz"} else ("ready" if ready else "not_ready")
            ),
            "ready": ready,
            "version": "2.0.0rc6",
            "rollout_mode": "target",
            "components": {"api": "ready"},
            "context": _context(request),
        },
    )


def _success(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/root")
    if path in {"/health", "/healthz", "/readiness", "/readyz"}:
        return _probe(request)
    payloads = {
        "/api/v1/search": {
            "items": [],
            "page": {"limit": 10},
            "meta": {},
            "context": _context(request),
        },
        "/api/v1/llm-search": {
            "query": "fixture",
            "items": [],
            "evidence": [],
            "meta": {},
            "usage": {},
            "context": _context(request),
        },
        "/api/v1/fetch": {
            "items": [],
            "meta": {},
            "context": _context(request),
        },
        "/api/v1/providers": {
            "items": [],
            "context": _context(request),
        },
    }
    return httpx.Response(
        200,
        headers=_headers(request.headers["X-Request-ID"]),
        json=payloads[path],
    )


def test_sync_client_covers_all_generated_operations_and_payloads() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _success(request)

    client = SouWenClient(
        "https://example.test/root/",
        token="application-fixture",
        transport=httpx.MockTransport(handler),
    )

    assert client.health(request_id="health-id").status == "ok"
    assert client.healthz(request_id="healthz-id").status == "ok"
    assert client.readiness(request_id="readiness-id").ready is True
    assert client.readyz(request_id="readyz-id").ready is True
    assert (
        client.search(
            SearchRequest(query="fixture", domains=["paper"]), request_id="search-id"
        ).page.limit
        == 10
    )
    assert (
        client.llm_search(
            LLMSearchRequest(
                query="fixture",
                providers=[ProviderRef(id="llm", kind="llm_search")],
                strategy="single",
            ),
            request_id="llm-id",
        ).query
        == "fixture"
    )
    assert (
        client.fetch(FetchRequest(targets=["https://example.com"]), request_id="fetch-id").items
        == []
    )
    assert client.list_providers(request_id="providers-id").items == []

    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/root/health"),
        ("GET", "/root/healthz"),
        ("GET", "/root/readiness"),
        ("GET", "/root/readyz"),
        ("POST", "/root/api/v1/search"),
        ("POST", "/root/api/v1/llm-search"),
        ("POST", "/root/api/v1/fetch"),
        ("GET", "/root/api/v1/providers"),
    ]
    assert requests[4].headers["Authorization"] == "Bearer application-fixture"
    assert requests[4].headers["X-SouWen-API-Major"] == "2"
    assert json.loads(requests[4].content) == {"domains": ["paper"], "query": "fixture"}
    client.close()


def test_first_business_request_preflights_before_sending_body() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(
            200,
            headers=_headers(request.headers["X-Request-ID"], major="3"),
            content=b"not-json",
        )

    client = SouWenClient("https://example.test", transport=httpx.MockTransport(handler))

    with pytest.raises(ApiMajorMismatchError) as exc_info:
        client.search(SearchRequest(query="fixture", domains=["paper"]))

    assert exc_info.value.expected == 2
    assert exc_info.value.received == "3"
    assert paths == ["/healthz"]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"token": "app"}, ("Bearer app", None)),
        (
            {"token": "app", "auth_channel": "x-souwen-token"},
            (None, "app"),
        ),
        (
            {"token": "app", "auth_channel": "x-souwen-token", "edge_token": "edge"},
            ("Bearer edge", "app"),
        ),
    ],
)
def test_auth_channels_are_explicit_and_never_fallback(kwargs, expected) -> None:
    observed: list[tuple[str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(
            (
                request.headers.get("Authorization"),
                request.headers.get("X-SouWen-Token"),
            )
        )
        return _probe(request)

    client = SouWenClient(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )
    client.healthz()

    assert observed == [expected]


def test_auth_and_reserved_header_conflicts_fail_before_network() -> None:
    with pytest.raises(ValueError, match="edge_token occupies Authorization"):
        SouWenClient("https://example.test", token="app", edge_token="edge")
    with pytest.raises(ValueError, match="reserved SDK headers"):
        SouWenClient(
            "https://example.test",
            headers={"Authorization": "Bearer hidden"},
        )


def test_canonical_api_error_preserves_safe_rate_limit_metadata_without_retry() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/healthz":
            return _probe(request)
        request_id = request.headers["X-Request-ID"]
        return httpx.Response(
            429,
            headers={
                **_headers(request_id),
                "Retry-After": "5",
                "X-RateLimit-Limit": "10",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "123",
            },
            json={
                "error": {
                    "code": "rate_limited",
                    "message": "rate limited",
                    "retryable": True,
                    "request_id": request_id,
                },
                "context": _context(request),
            },
        )

    client = SouWenClient("https://example.test", transport=httpx.MockTransport(handler))

    with pytest.raises(SouWenAPIError) as exc_info:
        client.search(SearchRequest(query="fixture", domains=["paper"]))

    error = exc_info.value
    assert error.status_code == 429
    assert error.payload.error.code == "rate_limited"
    assert error.retry_after == "5"
    assert error.rate_limit == {
        "X-RateLimit-Limit": "10",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "123",
    }
    assert paths == ["/healthz", "/api/v1/search"]


def test_response_correlation_and_rollout_are_fail_closed() -> None:
    def wrong_context(request: httpx.Request) -> httpx.Response:
        response = _probe(request)
        data = response.json()
        data["context"]["request_id"] = "different"
        return httpx.Response(response.status_code, headers=response.headers, json=data)

    with pytest.raises(ContractViolationError, match="context"):
        SouWenClient(
            "https://example.test",
            transport=httpx.MockTransport(wrong_context),
        ).healthz()

    def legacy_rollout(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=_headers(request.headers["X-Request-ID"], rollout="legacy"),
            json={},
        )

    with pytest.raises(ContractViolationError, match="Rollout-Mode"):
        SouWenClient(
            "https://example.test",
            transport=httpx.MockTransport(legacy_rollout),
        ).healthz()


def test_readiness_503_uses_its_generated_probe_response_model() -> None:
    client = SouWenClient(
        "https://example.test",
        transport=httpx.MockTransport(lambda request: _probe(request, ready=False)),
    )

    response = client.readyz()

    assert response.ready is False
    assert response.status == "not_ready"


def test_transport_error_and_client_ownership_are_explicit() -> None:
    def disconnected(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    owned = SouWenClient(
        "https://example.test",
        transport=httpx.MockTransport(disconnected),
    )
    with pytest.raises(SouWenTransportError):
        owned.healthz()
    owned.close()
    assert owned._client.is_closed is True

    injected = httpx.Client(transport=httpx.MockTransport(_success))
    borrowed = SouWenClient("https://example.test", http_client=injected)
    borrowed.close()
    assert injected.is_closed is False
    injected.close()


def test_default_timeout_covers_server_budget_and_allows_explicit_override() -> None:
    observed: list[dict[str, float]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request.extensions["timeout"])
        return _probe(request)

    client = SouWenClient(
        "https://example.test",
        transport=httpx.MockTransport(handler),
    )

    client.healthz()
    client.healthz(timeout=7)

    assert observed[0] == {"connect": 125.0, "read": 125.0, "write": 125.0, "pool": 125.0}
    assert observed[1] == {"connect": 7, "read": 7, "write": 7, "pool": 7}


@pytest.mark.asyncio
async def test_async_client_preflights_and_does_not_close_injected_client() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return _success(request)

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AsyncSouWenClient("https://example.test", http_client=injected)

    page = await client.search(SearchRequest(query="fixture", domains=["paper"]))

    assert page.page.limit == 10
    assert paths == ["/healthz", "/api/v1/search"]
    await client.aclose()
    assert injected.is_closed is False
    await injected.aclose()


def test_generated_models_validate_goldens_and_forbid_unknown_fields() -> None:
    goldens = json.loads(
        (REPOSITORY_ROOT / "tests/contracts/fixtures/target_api_contract_v2.json").read_text(
            encoding="utf-8"
        )
    )["goldens"]

    assert SearchPage.model_validate(goldens["search_partial_success"]).meta.partial is True
    with pytest.raises(ValidationError):
        SearchRequest(query="fixture", domains=["paper"], unknown="value")


def test_sdk_import_does_not_load_server_or_fastapi(tmp_path: Path) -> None:
    script = """
import json
import sys
from souwen.delivery.client_sdk import AsyncSouWenClient, SouWenClient
print(json.dumps({
    'sync': SouWenClient.__name__,
    'async': AsyncSouWenClient.__name__,
    'fastapi': 'fastapi' in sys.modules,
    'server': 'souwen.server.app' in sys.modules,
}))
"""
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "PYTHONPATH": str(REPOSITORY_ROOT / "src"),
    }

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert json.loads(completed.stdout) == {
        "sync": "SouWenClient",
        "async": "AsyncSouWenClient",
        "fastapi": False,
        "server": False,
    }
