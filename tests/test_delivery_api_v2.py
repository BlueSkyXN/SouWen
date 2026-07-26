"""Deterministic target Delivery API, auth, rollout, and composition tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from souwen.config import SouWenConfig
from souwen.delivery.api import (
    ProviderCatalogItem,
    ReadinessSnapshot,
    RolloutMode,
    RuntimeMetadata,
    TargetDeliveryServices,
    create_target_delivery_app,
    resolve_rollout_mode,
)
from souwen.modules.fetch.api import FetchBatch, FetchModuleService
from souwen.modules.llm_search.api import LLMSearchResult
from souwen.modules.search.api import SearchPage
from souwen.platform.provider_spi import (
    FetchMeta,
    PageInfo,
    ProviderError,
    ProviderErrorCode,
    Provenance,
    SearchMeta,
    Usage,
)
from souwen.providers.llm_sources.uniapi_ark_annotations.manifest import DEEPSEEK_ADAPTER_ID
from souwen.server.auth import check_target_user_auth
from souwen.server.limiter import rate_limit_target_data
from souwen.server.v2_runtime import TargetRuntime, build_target_runtime
from souwen.worker.browser_fetch.protocol import BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST


class _Search:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def search(self, _request, context, _execution):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SearchPage(
            items=(),
            page=PageInfo(limit=10),
            meta=SearchMeta(),
            context=context,
        )


class _LLMSearch:
    async def search(self, request, context, _execution):
        return LLMSearchResult(
            query=request.query,
            items=(),
            evidence=(),
            meta=SearchMeta(),
            usage=Usage(),
            context=context,
        )


class _Fetch:
    async def fetch(self, _request, context, _execution):
        return FetchBatch(items=(), meta=FetchMeta(), context=context)


@dataclass
class _AppFixture:
    client: TestClient
    search: _Search


def _services(
    search: _Search | None = None,
    fetch=None,
    readiness=None,
) -> TargetDeliveryServices:
    return TargetDeliveryServices(
        search=search or _Search(),
        llm_search=_LLMSearch(),
        fetch=fetch or _Fetch(),
        provider_items=(
            ProviderCatalogItem(
                provider="openalex",
                capabilities=("search",),
                availability="available",
                provenance=(Provenance(provider="openalex", outcome="success"),),
                reason="available",
            ),
        ),
        readiness=readiness
        or (
            lambda: ReadinessSnapshot(
                ready=True,
                components={"api": "ready", "openalex": "ready"},
            )
        ),
    )


def _app(
    *,
    search: _Search | None = None,
    fetch=None,
    require_user=lambda: None,
    rate_limit=lambda: None,
) -> _AppFixture:
    search = search or _Search()
    app = create_target_delivery_app(
        _services(search, fetch),
        RuntimeMetadata(
            version="2.0.0rc2",
            source_sha="a" * 40,
            rollout_mode=RolloutMode.TARGET,
            config_revision="config-r1",
        ),
        require_user=require_user,
        rate_limit=rate_limit,
    )
    return _AppFixture(TestClient(app, raise_server_exceptions=False), search)


def test_target_routes_emit_canonical_context_headers_and_catalog() -> None:
    fixture = _app()
    headers = {"X-Request-ID": "delivery-v2", "X-SouWen-API-Major": "2"}

    search = fixture.client.post(
        "/api/v1/search",
        headers=headers,
        json={"query": "fixture", "domains": ["paper"]},
    )
    llm = fixture.client.post(
        "/api/v1/llm-search",
        headers=headers,
        json={
            "query": "fixture",
            "providers": [{"id": DEEPSEEK_ADAPTER_ID, "kind": "llm_search"}],
            "strategy": "single",
        },
    )
    fetch = fixture.client.post(
        "/api/v1/fetch",
        headers=headers,
        json={"targets": ["https://example.com/page"]},
    )
    providers = fixture.client.get("/api/v1/providers", headers=headers)

    for response in (search, llm, fetch, providers):
        assert response.status_code == 200
        assert response.headers["x-request-id"] == "delivery-v2"
        assert response.headers["x-souwen-api-major"] == "2"
        assert response.headers["x-souwen-rollout-mode"] == "target"
        assert response.json()["context"] == {
            "request_id": "delivery-v2",
            "api_major": 2,
            "trace_id": None,
        }
    assert set(providers.json()) == {"items", "context"}
    assert providers.json()["items"][0]["provider"] == "openalex"
    assert fixture.search.calls == 1
    schema = fixture.client.app.openapi()
    assert schema["x-souwen-api-major"] == 2
    assert schema["x-souwen-rollout-mode"] == "target"
    for path, method in {
        "/api/v1/search": "post",
        "/api/v1/llm-search": "post",
        "/api/v1/fetch": "post",
        "/api/v1/providers": "get",
    }.items():
        responses = schema["paths"][path][method]["responses"]
        assert "400" in responses
        assert "422" not in responses
        assert responses["400"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
        for response in responses.values():
            assert {
                "X-SouWen-API-Major",
                "X-Request-ID",
                "X-SouWen-Rollout-Mode",
            } <= set(response["headers"])
    assert schema["components"]["securitySchemes"]["UserToken"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert schema["paths"]["/health"]["get"]["x-souwen-alias-of"] == "/healthz"
    assert schema["paths"]["/readiness"]["get"]["x-souwen-alias-of"] == "/readyz"
    assert "503" in schema["paths"]["/readyz"]["get"]["responses"]
    assert {
        "Retry-After",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    } <= set(schema["paths"]["/api/v1/search"]["post"]["responses"]["429"]["headers"])


def test_standalone_target_app_uses_canonical_404_and_excludes_admin() -> None:
    fixture = _app()

    unknown = fixture.client.get("/does-not-exist", headers={"X-Request-ID": "missing-route"})
    admin = fixture.client.get("/api/v1/admin/config")

    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"
    assert unknown.json()["context"]["request_id"] == "missing-route"
    assert unknown.headers["x-souwen-api-major"] == "2"
    assert admin.status_code == 404
    assert admin.json()["error"]["code"] == "not_found"


def test_runtime_openapi_satisfies_the_frozen_target_skeleton() -> None:
    runtime = _app().client.app.openapi()
    skeleton = json.loads(
        (
            Path(__file__).parent / "contracts" / "fixtures" / "target_openapi_skeleton_v2.json"
        ).read_text(encoding="utf-8")
    )

    assert runtime["x-souwen-api-major"] == skeleton["x-souwen-api-major"]
    assert runtime["x-souwen-contract-stage"] == skeleton["x-souwen-contract-stage"]
    assert (
        runtime["components"]["securitySchemes"]["UserToken"]
        == skeleton["components"]["securitySchemes"]["UserToken"]
    )
    assert set(skeleton["components"]["headers"]) <= set(runtime["components"]["headers"])
    assert set(skeleton["components"]["schemas"]) <= set(runtime["components"]["schemas"])
    for path, skeleton_path in skeleton["paths"].items():
        for method, skeleton_operation in skeleton_path.items():
            operation = runtime["paths"][path][method]
            assert operation["operationId"] == skeleton_operation["operationId"]
            assert set(skeleton_operation["responses"]) <= set(operation["responses"])
            if "security" in skeleton_operation:
                assert operation["security"] == skeleton_operation["security"]
            if "x-souwen-alias-of" in skeleton_operation:
                assert operation["x-souwen-alias-of"] == skeleton_operation["x-souwen-alias-of"]


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ProviderError(ProviderErrorCode.INVALID_REQUEST), 400, "invalid_request"),
        (ProviderError(ProviderErrorCode.PAYLOAD_TOO_LARGE), 413, "payload_too_large"),
        (ProviderError(ProviderErrorCode.UNSUPPORTED_MEDIA_TYPE), 415, "unsupported_media_type"),
        (
            ProviderError(ProviderErrorCode.WORKER_PROTOCOL_MISMATCH),
            409,
            "worker_protocol_mismatch",
        ),
        (ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED), 504, "provider_timeout"),
    ],
)
def test_target_provider_failures_keep_specialist_statuses(error, status_code, code) -> None:
    fixture = _app(search=_Search(error))
    response = fixture.client.post(
        "/api/v1/search",
        json={"query": "fixture", "domains": ["paper"]},
    )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["request_id"] == response.json()["context"]["request_id"]


def test_target_validation_is_400_and_api_major_mismatch_is_409() -> None:
    fixture = _app()
    invalid = fixture.client.post(
        "/api/v1/search",
        json={"query": "fixture", "domains": ["paper"], "unknown": "secret-value"},
    )
    mismatch = fixture.client.post(
        "/api/v1/search",
        headers={"X-SouWen-API-Major": "1"},
        json={"query": "fixture", "domains": ["paper"]},
    )

    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_request"
    assert "secret-value" not in invalid.text
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "api_major_mismatch"
    assert fixture.search.calls == 0


def test_target_method_mismatch_is_a_canonical_client_error() -> None:
    response = _app().client.get("/api/v1/search")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.headers["allow"] == "POST"


def test_provider_rate_limit_always_carries_required_headers() -> None:
    response = _app(
        search=_Search(
            ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id="openalex",
                retry_after_seconds=2.2,
            )
        )
    ).client.post(
        "/api/v1/search",
        json={"query": "fixture", "domains": ["paper"]},
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.headers["retry-after"] == "3"
    assert response.headers["x-ratelimit-limit"] == "unknown"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert response.headers["x-ratelimit-reset"].isdigit()


def test_fetch_all_rate_limited_preserves_maximum_provider_retry_after() -> None:
    class _RateLimitedManager:
        async def execute(self, _adapter_id, request, _context, _execution):
            retry_after = 20 if str(request.target).endswith("/slow") else 5
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id="builtin-fetch",
                retry_after_seconds=retry_after,
            )

    response = _app(fetch=FetchModuleService(_RateLimitedManager())).client.post(
        "/api/v1/fetch",
        json={"targets": ["https://example.com/fast", "https://example.com/slow"]},
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.headers["retry-after"] == "20"


def test_probe_aliases_share_handler_payload_and_need_no_auth() -> None:
    fixture = _app(require_user=lambda: (_ for _ in ()).throw(HTTPException(status_code=401)))
    headers = {"X-Request-ID": "same-probe"}

    healthz = fixture.client.get("/healthz", headers=headers)
    health = fixture.client.get("/health", headers=headers, follow_redirects=False)
    readyz = fixture.client.get("/readyz", headers=headers)
    readiness = fixture.client.get("/readiness", headers=headers, follow_redirects=False)

    assert healthz.status_code == health.status_code == 200
    assert healthz.json() == health.json()
    assert readyz.status_code == readiness.status_code == 200
    assert readyz.json() == readiness.json()
    assert "location" not in health.headers
    assert "location" not in readiness.headers


def test_not_ready_probe_is_503_and_health_stays_live() -> None:
    services = _services(
        readiness=lambda: ReadinessSnapshot(
            ready=False,
            components={"api": "ready", "browser_worker": "not_ready"},
            error="required target runtime component is not ready",
        )
    )
    app = create_target_delivery_app(
        services,
        RuntimeMetadata(
            version="2.0.0rc2",
            source_sha="a" * 40,
            rollout_mode=RolloutMode.TARGET,
        ),
        require_user=lambda: None,
        rate_limit=lambda: None,
    )
    client = TestClient(app)

    health = client.get("/healthz")
    readiness = client.get("/readyz")

    assert health.status_code == 200
    assert readiness.status_code == 503
    assert readiness.json()["ready"] is False
    assert readiness.json()["components"]["browser_worker"] == "not_ready"


@pytest.mark.parametrize(
    ("config", "headers", "expected"),
    [
        (SouWenConfig(), {}, 401),
        (SouWenConfig(guest_enabled=True), {}, 200),
        (SouWenConfig(user_password=""), {}, 200),
        (SouWenConfig(user_password="user"), {"Authorization": "Bearer user"}, 200),
        (SouWenConfig(admin_password="admin"), {"Authorization": "Bearer admin"}, 200),
        (
            SouWenConfig(user_password="user"),
            {"Authorization": "Bearer user", "X-SouWen-Token": "wrong"},
            401,
        ),
        (
            SouWenConfig(user_password="user"),
            {"Authorization": "Bearer outer", "X-SouWen-Token": "user"},
            200,
        ),
        (
            SouWenConfig(user_password="user"),
            {"Authorization": "Bearer user", "X-SouWen-Token": ""},
            401,
        ),
    ],
)
def test_target_auth_is_fail_closed_and_custom_header_is_authoritative(
    monkeypatch, config, headers, expected
) -> None:
    monkeypatch.setattr("souwen.server.auth.get_config", lambda: config)
    fixture = _app(require_user=check_target_user_auth)

    response = fixture.client.get("/api/v1/providers", headers=headers)

    assert response.status_code == expected
    if expected == 401:
        assert response.json()["error"]["code"] == "unauthenticated"


def test_target_rate_limit_uses_credential_digest_and_custom_header_precedence(monkeypatch) -> None:
    identities: list[str] = []
    monkeypatch.setattr("souwen.server.limiter._target_data_limiter.check", identities.append)
    fixture = _app(rate_limit=rate_limit_target_data)

    fixture.client.get("/api/v1/providers", headers={"Authorization": "Bearer user-token"})
    fixture.client.get(
        "/api/v1/providers",
        headers={"Authorization": "Bearer ignored", "X-SouWen-Token": "user-token"},
    )

    assert identities[0] == identities[1]
    assert identities[0].startswith("credential:")
    assert "user-token" not in identities[0]


def test_local_target_limiter_error_keeps_canonical_body_and_headers() -> None:
    def limited() -> None:
        raise HTTPException(
            status_code=429,
            headers={
                "Retry-After": "5",
                "X-RateLimit-Limit": "60",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "123456",
            },
        )

    response = _app(rate_limit=limited).client.get("/api/v1/providers")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert response.headers["retry-after"] == "5"
    assert response.headers["x-ratelimit-limit"] == "60"
    assert response.headers["x-ratelimit-remaining"] == "0"
    assert response.headers["x-ratelimit-reset"] == "123456"


@pytest.mark.asyncio
async def test_runtime_catalog_keeps_uniapi_missing_fields_safe_and_nonblocking(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SOUWEN_BROWSER_WORKER_TOKEN", raising=False)
    runtime = build_target_runtime(SouWenConfig(sources={DEEPSEEK_ADAPTER_ID: {"enabled": True}}))

    by_id = {item.provider: item for item in runtime.services.provider_items}
    assert {"openalex-search", "builtin-fetch"} <= set(runtime.manager.eligible_adapter_ids)
    assert by_id[DEEPSEEK_ADAPTER_ID].availability == "unavailable"
    assert by_id[DEEPSEEK_ADAPTER_ID].missing_fields == (
        "llm_search_gateways.uniapi.api_key",
        "llm_search_gateways.uniapi.base_url",
    )
    assert "UNIAPI_API_KEY" not in repr(runtime.services.provider_items)
    readiness = await runtime.services.readiness()
    assert readiness.ready is True
    assert readiness.components["browser_worker"] == "disabled"


@pytest.mark.asyncio
async def test_enabled_browser_worker_is_required_for_target_readiness(monkeypatch) -> None:
    class _Worker:
        def __init__(self, *, fail: bool) -> None:
            self.fail = fail

        async def readiness(self, _context, _execution):
            if self.fail:
                raise ProviderError(ProviderErrorCode.WORKER_NOT_READY)
            return SimpleNamespace(evidence=SimpleNamespace(source_sha="a" * 40))

        async def fetch(self, *_args):  # pragma: no cover - composition protocol only
            raise AssertionError("not called")

        async def close(self) -> None:
            return None

    unavailable = _Worker(fail=True)
    monkeypatch.setattr("souwen.server.v2_runtime._browser_client", lambda: unavailable)
    runtime = build_target_runtime(SouWenConfig())
    snapshot = await runtime.services.readiness()

    assert snapshot.ready is False
    assert snapshot.components["browser_worker"] == "not_ready"

    ready_worker = _Worker(fail=False)
    monkeypatch.setattr("souwen.server.v2_runtime._browser_client", lambda: ready_worker)
    runtime = build_target_runtime(SouWenConfig())
    snapshot = await runtime.services.readiness()

    assert snapshot.ready is True
    assert snapshot.components["browser_worker"] == "ready"
    assert snapshot.worker_source_sha == "a" * 40


def test_composition_root_requires_the_shared_browser_inventory_digest(monkeypatch) -> None:
    monkeypatch.setenv("SOUWEN_BROWSER_WORKER_TOKEN", "w" * 48)

    runtime = build_target_runtime(SouWenConfig())

    assert runtime.browser_client is not None
    assert (
        runtime.browser_client._expected_inventory_digest
        == BROWSER_WORKER_PROVIDER_INVENTORY_DIGEST
    )


@pytest.mark.asyncio
async def test_runtime_close_attempts_browser_after_provider_close_failure() -> None:
    class _Manager:
        async def close_all(self) -> None:
            raise RuntimeError("provider close failed")

    class _Worker:
        closed = False

        async def close(self) -> None:
            self.closed = True

    worker = _Worker()
    runtime = TargetRuntime(
        services=_services(),
        metadata=RuntimeMetadata(
            version="2.0.0rc2",
            source_sha="a" * 40,
            rollout_mode=RolloutMode.TARGET,
        ),
        manager=_Manager(),
        browser_client=worker,
    )

    with pytest.raises(RuntimeError, match="provider close failed"):
        await runtime.close()

    assert worker.closed is True


def test_standalone_app_closes_its_injected_runtime() -> None:
    closed = False

    async def close() -> None:
        nonlocal closed
        closed = True

    app = create_target_delivery_app(
        _services(),
        RuntimeMetadata(
            version="2.0.0rc2",
            source_sha="a" * 40,
            rollout_mode=RolloutMode.TARGET,
        ),
        require_user=lambda: None,
        rate_limit=lambda: None,
        closer=close,
    )

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200

    assert closed is True


def test_rollout_mode_is_strict_and_target_router_precedes_legacy_fetch(tmp_path) -> None:
    assert resolve_rollout_mode("legacy") is RolloutMode.LEGACY
    assert resolve_rollout_mode(" target ") is RolloutMode.TARGET
    with pytest.raises(ValueError):
        resolve_rollout_mode("canary")

    repo_src = str(Path(__file__).resolve().parents[1] / "src")
    script = """
import sys

sys.path.insert(0, sys.argv[1])

from souwen.server.app import app

def iter_routes(routes, prefix=''):
    for route in routes:
        original_router = getattr(route, 'original_router', None)
        include_context = getattr(route, 'include_context', None)
        if original_router is not None and include_context is not None:
            yield from iter_routes(original_router.routes, prefix + include_context.prefix)
            continue
        path = getattr(route, 'path', None)
        if path is not None:
            yield prefix + path, route

matches = [
    route for path, route in iter_routes(app.routes)
    if path == '/api/v1/fetch'
    and 'POST' in getattr(route, 'methods', set())
]
print(matches[0].response_model.__name__)
"""
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "SOUWEN_SOURCE_SHA": "a" * 40,
        "SOUWEN_V2_ROLLOUT": "target",
        "PYTHONPATH": os.pathsep.join(
            path for path in (repo_src, os.environ.get("PYTHONPATH")) if path
        ),
    }
    env.pop("SOUWEN_BROWSER_WORKER_TOKEN", None)
    completed = subprocess.run(
        [sys.executable, "-c", script, repo_src],
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "FetchBatch"


def test_target_host_replaces_non_ascii_request_id(tmp_path) -> None:
    script = """
import asyncio
import json

from souwen.server.app import app

async def main():
    messages = []

    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(message):
        messages.append(message)

    await app(
        {
            'type': 'http',
            'asgi': {'version': '3.0'},
            'http_version': '1.1',
            'method': 'GET',
            'scheme': 'http',
            'path': '/healthz',
            'raw_path': b'/healthz',
            'query_string': b'',
            'headers': [(b'x-request-id', b'\\xc3\\xa9')],
            'client': ('127.0.0.1', 12345),
            'server': ('testserver', 80),
        },
        receive,
        send,
    )
    start = next(message for message in messages if message['type'] == 'http.response.start')
    body = b''.join(
        message.get('body', b'')
        for message in messages
        if message['type'] == 'http.response.body'
    )
    headers = dict(start['headers'])
    payload = json.loads(body)
    request_id = headers[b'x-request-id'].decode('ascii')
    assert start['status'] == 200
    assert request_id.isascii()
    assert payload['context']['request_id'] == request_id

asyncio.run(main())
print('ok')
"""
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "SOUWEN_V2_ROLLOUT": "target",
    }
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.stdout.strip() == "ok"
