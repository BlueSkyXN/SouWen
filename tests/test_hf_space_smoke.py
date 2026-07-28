"""Deterministic tests for the target-only HFS smoke."""

from __future__ import annotations

import json

import pytest

from scripts import hf_space_smoke as smoke


def test_parse_args_preserves_deployment_workflow_interface() -> None:
    args = smoke.parse_args(
        [
            "--base-url",
            "http://127.0.0.1:49265",
            "--expected-version",
            "2.0.0rc3",
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
    assert payload["checks"][0]["outcome"] == "SKIP"
    assert "HFS target smoke" in markdown_path.read_text(encoding="utf-8")


def test_target_openapi_path_set_is_exact() -> None:
    assert smoke.TARGET_PATHS == {
        "/api/v1/search",
        "/api/v1/llm-search",
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
                    "version": "2.0.0rc3",
                    "config_revision": "source-test",
                },
            )

    args = smoke.parse_args(["--expected-version", "2.0.0rc3", "--require-target-runtime"])

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


def test_missing_required_llm_provider_is_reported_as_a_failed_check(monkeypatch, tmp_path) -> None:
    providers = [
        {
            "provider": "openalex",
            "availability": "available",
            "capabilities": ["search"],
        },
        {
            "provider": "builtin",
            "availability": "available",
            "capabilities": ["fetch"],
        },
    ]

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def json(self, path, **_kwargs):
            if path == "/api/v1/search":
                return 200, {}, {"items": []}
            if path == "/api/v1/fetch":
                return 200, {}, {"items": [{"status": "success", "content": "fixture"}]}
            raise AssertionError(path)

    monkeypatch.setattr(smoke, "Client", Client)
    monkeypatch.setattr(
        smoke,
        "_surface_checks",
        lambda _client, _args, _checks: providers,
    )
    report = tmp_path / "capability.json"

    assert smoke.main(["--mode", "capability", "--json-report", str(report)]) == 1

    payload = json.loads(report.read_text(encoding="utf-8"))
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["search_live"]["outcome"] == "PASS"
    assert checks["llm_search_live"]["outcome"] == "FAIL"
    assert checks["llm_search_live"]["detail"] == "no available llm_search provider"
    assert checks["fetch_live"]["outcome"] == "PASS"


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

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def json(self, path, **kwargs):
            if path == "/api/v1/search":
                provider = kwargs["payload"]["providers"][0]["id"]
                calls.append(provider)
                if provider == "openalex":
                    return 503, {}, {"error": {"code": "upstream_unavailable"}}
                return 200, {}, {"items": []}
            if path == "/api/v1/llm-search":
                return 200, {}, {"evidence": [], "usage": {}}
            if path == "/api/v1/fetch":
                return 200, {}, {"items": [{"status": "success", "content": "fixture"}]}
            raise AssertionError(path)

    monkeypatch.setattr(smoke, "Client", Client)
    monkeypatch.setattr(smoke, "_surface_checks", lambda _client, _args, _checks: providers)
    report = tmp_path / "capability.json"

    assert smoke.main(["--mode", "capability", "--json-report", str(report)]) == 0
    assert calls == ["openalex", "crossref"]
    checks = {
        item["name"]: item for item in json.loads(report.read_text(encoding="utf-8"))["checks"]
    }
    assert checks["search_live"]["detail"] == "crossref: 0 results"
