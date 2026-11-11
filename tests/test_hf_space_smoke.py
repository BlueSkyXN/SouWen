"""Deterministic tests for the target-only HFS smoke."""

from __future__ import annotations

import json

import pytest

from scripts import hf_space_smoke as smoke
from souwen.common_runtime.security import redaction as canonical_redaction


def test_parse_args_preserves_deployment_workflow_interface() -> None:
    args = smoke.parse_args(
        [
            "--base-url",
            "http://127.0.0.1:49265",
            "--expected-version",
            "2.0.0rc6",
            "--expected-source-sha",
            "a" * 40,
            "--expected-wrapper-sha",
            "b" * 40,
            "--require-target-runtime",
            "--surface-only",
        ]
    )
    assert args.surface_only is True
    assert args.require_target_runtime is True
    assert args.expected_source_sha == "a" * 40


def test_client_keeps_edge_and_application_auth_separate(monkeypatch) -> None:
    captured = {}

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)
    client = smoke.Client(
        "https://example.invalid",
        edge_token="edge-canary",
        app_token="app-canary",
        timeout=3,
    )
    status, _headers, _body = client.request("/healthz")
    assert status == 200
    assert captured["headers"]["Authorization"] == "Bearer edge-canary"
    assert captured["headers"]["X-souwen-token"] == "app-canary"


def test_client_can_send_a_completely_anonymous_negative_probe(monkeypatch) -> None:
    captured = {}

    class Response:
        status = 401
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)
    client = smoke.Client(
        "https://example.invalid",
        edge_token="edge-canary",
        app_token="app-canary",
        timeout=3,
    )

    status, _headers, _body = client.request("/api/v1/providers", anonymous=True)

    assert status == 401
    assert "authorization" not in captured["headers"]
    assert "x-souwen-token" not in captured["headers"]


def test_offline_mode_writes_bounded_reports(tmp_path) -> None:
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"
    assert (
        smoke.main(
            [
                "--mode",
                "offline",
                "--json-report",
                str(json_path),
                "--markdown-report",
                str(markdown_path),
            ]
        )
        == 0
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["overall"] == "PASS"
    assert payload["environment"] == {
        "expected_version": None,
        "expected_source_sha": None,
        "expected_wrapper_sha": None,
        "require_target_runtime": False,
    }
    assert payload["checks"][0]["outcome"] == "SKIP"
    assert "HFS target smoke" in markdown_path.read_text(encoding="utf-8")


def test_report_records_bounded_provenance_without_auth_tokens(tmp_path) -> None:
    json_path = tmp_path / "report.json"
    args = smoke.parse_args(
        [
            "--mode",
            "capability",
            "--json-report",
            str(json_path),
            "--expected-version",
            "2.0.0rc6",
            "--expected-source-sha",
            "a" * 40,
            "--expected-wrapper-sha",
            "b" * 40,
            "--require-target-runtime",
            "--bearer-token",
            "application-secret-canary",
            "--hf-space-token",
            "edge-secret-canary",
        ]
    )

    smoke._write_reports(
        args,
        "capability",
        [smoke.Check("healthz", "PASS", "fixture")],
    )

    report_text = json_path.read_text(encoding="utf-8")
    payload = json.loads(report_text)
    assert payload["environment"] == {
        "expected_version": "2.0.0rc6",
        "expected_source_sha": "a" * 40,
        "expected_wrapper_sha": "b" * 40,
        "require_target_runtime": True,
    }
    assert "application-secret-canary" not in report_text
    assert "edge-secret-canary" not in report_text


def test_target_openapi_path_set_is_exact() -> None:
    assert smoke.TARGET_PATHS == {
        "/api/v1/search",
        "/api/v1/fetch",
        "/api/v1/providers",
        "/health",
        "/healthz",
        "/readiness",
        "/readyz",
    }


def test_probe_accepts_lowercase_http_response_headers() -> None:
    class Client:
        def json(self, path, **_kwargs):
            return (
                200,
                {"x-souwen-api-major": "2"},
                {
                    "rollout_mode": "target",
                    "version": "2.0.0rc6",
                    "config_revision": "source-test",
                },
            )

    args = smoke.parse_args(["--expected-version", "2.0.0rc6", "--require-target-runtime"])

    detail, payload = smoke._probe(Client(), "/healthz", args)

    assert detail == "/healthz target runtime verified"
    assert payload["rollout_mode"] == "target"


def test_readiness_probe_requires_browser_worker_evidence() -> None:
    class Client:
        def json(self, path, **_kwargs):
            return (
                200,
                {"x-souwen-api-major": "2"},
                {
                    "rollout_mode": "target",
                    "config_revision": "source-test",
                    "source_sha": "a" * 40,
                    "components": {"api": "ready"},
                },
            )

    args = smoke.parse_args(["--require-target-runtime"])

    with pytest.raises(smoke.SmokeFailure, match="browser worker"):
        smoke._probe(Client(), "/readyz", args)


def test_search_live_uses_bounded_provider_fallback(monkeypatch, tmp_path) -> None:
    providers = [
        {
            "provider": provider,
            "availability": "available",
            "capabilities": ["search"],
        }
        for provider in ("openalex", "crossref", "semantic_scholar")
    ]
    providers.extend(
        [
            {
                "provider": "fixture-llm",
                "availability": "available",
                "capabilities": ["llm_search"],
            },
            {
                "provider": "builtin-fetch",
                "availability": "available",
                "capabilities": ["fetch"],
            },
        ]
    )
    calls: list[str] = []
    default_payloads: list[dict] = []
    fetch_strategies: list[str] = []

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def json(self, path, **kwargs):
            if path == "/api/v1/search":
                if "providers" not in kwargs["payload"]:
                    default_payloads.append(kwargs["payload"])
                    calls.append("default")
                    return 200, {}, {"items": [], "meta": {"requested": ["crossref"]}}
                provider = kwargs["payload"]["providers"][0]["id"]
                calls.append(provider)
                if provider == "crossref":
                    return 503, {}, {"error": {"code": "upstream_unavailable"}}
                return 200, {}, {"items": []}
            if path == "/api/v1/fetch":
                fetch_strategies.append(kwargs["payload"]["strategy"])
                return (
                    200,
                    {},
                    {"items": [{"status": "success", "content": "Example Domain fixture"}]},
                )
            raise AssertionError(path)

    monkeypatch.setattr(smoke, "Client", Client)
    monkeypatch.setattr(smoke, "_surface_checks", lambda _client, _args, _checks: providers)
    report = tmp_path / "capability.json"

    assert smoke.main(["--mode", "capability", "--json-report", str(report)]) == 0
    assert calls == ["default", "crossref", "openalex"]
    assert default_payloads == [
        {
            "query": "retrieval augmented generation",
            "domains": ["paper"],
            "page": {"limit": 3},
        }
    ]
    assert fetch_strategies == ["fallback", "fanout"]
    checks = {
        item["name"]: item for item in json.loads(report.read_text(encoding="utf-8"))["checks"]
    }
    assert checks["search_default_live"]["detail"] == "crossref: 0 results"
    assert checks["search_live"]["detail"] == "openalex: 0 results"


@pytest.mark.parametrize(
    "field",
    (
        "access_token",
        "api_key",
        "session_id",
        "x_souwen_token",
        "unregistered_source_api_key",
    ),
)
def test_admin_config_classifier_covers_the_canonical_secret_inventory(field: str) -> None:
    assert smoke._is_secret_field(field)


def test_smoke_secret_field_inventory_stays_in_lockstep_with_the_server() -> None:
    assert smoke._SECRET_KEYWORDS == canonical_redaction._SECRET_KEYWORDS
    assert smoke._COMPACT_SECRET_FIELDS == canonical_redaction._COMPACT_SECRET_FIELDS


@pytest.mark.parametrize(
    "field",
    ("api_key", "private-key", "clientSecret", "XSessionID", "refreshToken"),
)
def test_admin_config_classifier_matches_separator_and_camel_case_fields(field: str) -> None:
    assert smoke._is_secret_field(field)


def test_unredacted_admin_config_is_a_required_failure() -> None:
    assert smoke._unredacted_secret_fields(
        {
            "sources": {
                "fixture": {
                    "api_key": "plain-text-secret",
                    "privateKey": "plain-text-private-key",
                }
            }
        }
    ) == ["sources.fixture.api_key", "sources.fixture.privateKey"]
