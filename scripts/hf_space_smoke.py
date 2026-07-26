#!/usr/bin/env python3
"""Target-only HFS deployment smoke with separate edge and application auth."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://blueskyxn-souwen.hf.space"
TARGET_PATHS = {
    "/api/v1/fetch",
    "/api/v1/llm-search",
    "/api/v1/providers",
    "/api/v1/search",
    "/health",
    "/healthz",
    "/readiness",
    "/readyz",
}
FETCH_PROBE_PATH = "scripts/fixtures/hf-space-fetch-probe.html"
FETCH_PROBE_MARKER = "SOUWEN_IMMUTABLE_FETCH_PROBE_V1"


@dataclass(slots=True)
class Check:
    name: str
    outcome: str
    detail: str
    required: bool = True
    duration_seconds: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


class SmokeFailure(RuntimeError):
    pass


class Client:
    def __init__(
        self,
        base_url: str,
        *,
        edge_token: str | None,
        app_token: str | None,
        timeout: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.edge_token = edge_token
        self.app_token = app_token
        self.timeout = timeout

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        application_auth: bool = True,
    ) -> tuple[int, dict[str, str], bytes]:
        headers = {"Accept": "application/json", "User-Agent": "SouWen-HFS-Smoke/2"}
        if self.edge_token:
            headers["Authorization"] = f"Bearer {self.edge_token}"
            if application_auth and self.app_token:
                headers["X-SouWen-Token"] = self.app_token
        elif application_auth and self.app_token:
            headers["Authorization"] = f"Bearer {self.app_token}"
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers.items()), response.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()
        except URLError as exc:
            raise SmokeFailure(f"request failed: {type(exc.reason).__name__}") from exc

    def json(self, path: str, **kwargs: Any) -> tuple[int, dict[str, str], Any]:
        status, headers, body = self.request(path, **kwargs)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SmokeFailure(f"{path} returned non-JSON content") from exc
        return status, headers, payload


def _record(checks: list[Check], name: str, callback, *, required: bool = True) -> Any:
    started = time.perf_counter()
    try:
        detail, value = callback()
    except Exception as exc:  # noqa: BLE001 - public report retains only bounded exception type.
        checks.append(
            Check(
                name=name,
                outcome="FAIL" if required else "WARN",
                detail=type(exc).__name__,
                required=required,
                duration_seconds=time.perf_counter() - started,
            )
        )
        return None
    checks.append(
        Check(
            name=name,
            outcome="PASS",
            detail=detail,
            required=required,
            duration_seconds=time.perf_counter() - started,
        )
    )
    return value


def _expect(condition: bool, detail: str) -> None:
    if not condition:
        raise SmokeFailure(detail)


def _probe(client: Client, path: str, args: argparse.Namespace):
    status, headers, payload = client.json(path, application_auth=False)
    _expect(status == 200, f"{path} status {status}")
    _expect(isinstance(payload, dict), f"{path} payload")
    _expect(payload.get("rollout_mode") == "target", f"{path} runtime identity")
    api_major = next(
        (value for name, value in headers.items() if name.lower() == "x-souwen-api-major"),
        None,
    )
    _expect(api_major == "2", f"{path} API major")
    if args.expected_version:
        _expect(payload.get("version") == args.expected_version, f"{path} version")
    if args.expected_source_sha:
        _expect(payload.get("source_sha") == args.expected_source_sha, f"{path} source SHA")
    if args.expected_wrapper_sha:
        _expect(payload.get("wrapper_sha") == args.expected_wrapper_sha, f"{path} wrapper SHA")
    if args.require_target_runtime:
        _expect(bool(payload.get("config_revision")), f"{path} config revision")
        components = payload.get("components") or {}
        _expect(components.get("browser_worker") == "ready", f"{path} browser worker")
        _expect(
            payload.get("worker_source_sha") == payload.get("source_sha"),
            f"{path} worker source SHA",
        )
    return f"{path} target runtime verified", payload


def _surface_checks(client: Client, args: argparse.Namespace, checks: list[Check]) -> list[dict]:
    _record(checks, "healthz", lambda: _probe(client, "/healthz", args))
    _record(checks, "readyz", lambda: _probe(client, "/readyz", args))

    def openapi():
        status, _headers, payload = client.json("/openapi.json", application_auth=False)
        _expect(status == 200, f"openapi status {status}")
        _expect(set(payload.get("paths", {})) == TARGET_PATHS, "non-canonical OpenAPI paths")
        _expect(payload.get("x-souwen-contract-stage") == "target_only", "contract stage")
        return "8 canonical paths", payload

    _record(checks, "openapi", openapi)

    def panel():
        status, _headers, body = client.request("/panel", application_auth=False)
        _expect(status == 200 and b'id="root"' in body, f"panel status {status}")
        return "Calm Precision panel entry present", None

    _record(checks, "panel", panel)

    def whoami():
        status, _headers, payload = client.json("/api/v1/whoami")
        _expect(status == 200, f"whoami status {status}")
        _expect(payload.get("role") == "admin", "application token is not admin")
        if args.fail_admin_open:
            _expect(payload.get("admin_open") is False, "admin_open must be false")
        return "admin application auth verified", payload

    _record(checks, "whoami", whoami)

    if client.app_token:

        def anonymous_admin():
            status, _headers, _payload = client.json("/api/v1/admin/ping", application_auth=False)
            _expect(status in {401, 403}, f"anonymous admin status {status}")
            return "anonymous admin rejected", None

        _record(checks, "anonymous_admin_rejected", anonymous_admin)

    def providers():
        status, _headers, payload = client.json("/api/v1/providers")
        _expect(status == 200 and isinstance(payload.get("items"), list), "provider catalog")
        return f"{len(payload['items'])} provider packages", payload["items"]

    return _record(checks, "providers", providers) or []


def _first_available(items: list[dict], capability: str, preferred: tuple[str, ...]) -> str:
    available = {
        item.get("provider")
        for item in items
        if item.get("availability") == "available" and capability in item.get("capabilities", [])
    }
    for provider in preferred:
        if provider in available:
            return provider
    if available:
        return sorted(available)[0]
    raise SmokeFailure(f"no available {capability} provider")


def _capability_checks(
    client: Client,
    args: argparse.Namespace,
    checks: list[Check],
    providers: list[dict],
) -> None:
    def search():
        search_provider = _first_available(providers, "search", ("openalex", "duckduckgo"))
        status, _headers, payload = client.json(
            "/api/v1/search",
            method="POST",
            payload={
                "query": "retrieval augmented generation",
                "domains": ["paper"],
                "providers": [{"id": search_provider, "kind": "search"}],
                "page": {"limit": 3},
            },
        )
        _expect(status == 200 and isinstance(payload.get("items"), list), f"search {status}")
        return f"{search_provider}: {len(payload['items'])} results", payload

    _record(checks, "search_live", search)

    def llm_search():
        llm_provider = _first_available(providers, "llm_search", ())
        status, _headers, payload = client.json(
            "/api/v1/llm-search",
            method="POST",
            payload={
                "query": "What is retrieval augmented generation?",
                "providers": [{"id": llm_provider, "kind": "llm_search"}],
                "strategy": "single",
                "max_results_per_provider": 3,
            },
        )
        _expect(status == 200 and isinstance(payload.get("evidence"), list), f"llm {status}")
        _expect(isinstance(payload.get("usage"), dict), "llm usage missing")
        return f"{llm_provider}: {len(payload['evidence'])} evidence items", payload

    _record(checks, "llm_search_live", llm_search)

    target = "https://example.com/"
    if args.expected_source_sha:
        target = (
            "https://raw.githubusercontent.com/BlueSkyXN/SouWen/"
            f"{args.expected_source_sha}/{FETCH_PROBE_PATH}"
        )

    def fetch():
        fetch_provider = _first_available(
            providers,
            "fetch",
            ("builtin-fetch", "jina_reader"),
        )
        status, _headers, payload = client.json(
            "/api/v1/fetch",
            method="POST",
            payload={
                "targets": [target],
                "providers": [{"id": fetch_provider, "kind": "fetch"}],
                "strategy": "fallback",
            },
        )
        items = payload.get("items") if isinstance(payload, dict) else None
        _expect(status == 200 and isinstance(items, list) and items, f"fetch {status}")
        _expect(items[0].get("status") == "success", "fetch result failed")
        if args.expected_source_sha:
            _expect(FETCH_PROBE_MARKER in (items[0].get("content") or ""), "fetch marker")
        return f"{fetch_provider}: immutable target fetched", payload

    _record(checks, "fetch_live", fetch)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default=os.environ.get("SOUWEN_HF_SPACE_URL", DEFAULT_BASE_URL)
    )
    parser.add_argument("--expected-version", default=os.environ.get("EXPECTED_SOUWEN_VERSION"))
    parser.add_argument(
        "--expected-source-sha", default=os.environ.get("EXPECTED_SOUWEN_SOURCE_SHA")
    )
    parser.add_argument(
        "--expected-wrapper-sha", default=os.environ.get("EXPECTED_SOUWEN_WRAPPER_SHA")
    )
    parser.add_argument("--require-target-runtime", action="store_true")
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=float(os.environ.get("SOUWEN_SMOKE_REQUEST_TIMEOUT", "25")),
    )
    parser.add_argument(
        "--report-file",
        "--markdown-report",
        dest="report_file",
        default=os.environ.get("SOUWEN_SMOKE_REPORT_FILE"),
    )
    parser.add_argument(
        "--json-file",
        "--json-report",
        dest="json_file",
        default=os.environ.get("SOUWEN_SMOKE_JSON_FILE"),
    )
    parser.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    parser.add_argument("--bearer-token", default=os.environ.get("SOUWEN_SMOKE_BEARER_TOKEN"))
    parser.add_argument("--hf-space-token", default=os.environ.get("SOUWEN_HF_SPACE_TOKEN"))
    parser.add_argument(
        "--fail-admin-open",
        dest="fail_admin_open",
        action="store_true",
        default=os.environ.get("SOUWEN_SMOKE_FAIL_ADMIN_OPEN", "").lower()
        in {"1", "true", "yes", "on"},
    )
    parser.add_argument("--mode", choices=("surface", "capability", "offline"))
    parser.add_argument("--surface-only", action="store_true")
    return parser.parse_args(argv)


def _write_reports(args: argparse.Namespace, mode: str, checks: list[Check]) -> None:
    overall = "FAIL" if any(item.required and item.outcome == "FAIL" for item in checks) else "PASS"
    payload = {
        "schema_version": 1,
        "script": "hf_space_smoke",
        "mode": mode,
        "overall": overall,
        "base_url": args.base_url.rstrip("/"),
        "checks": [asdict(item) for item in checks],
    }
    lines = [
        "# SouWen HFS target smoke",
        "",
        f"- Overall: **{overall}**",
        "",
        "| Check | Outcome | Detail |",
        "|---|---|---|",
    ]
    lines.extend(f"| `{item.name}` | {item.outcome} | {item.detail} |" for item in checks)
    markdown = "\n".join(lines) + "\n"
    if args.json_file:
        Path(args.json_file).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.report_file:
        Path(args.report_file).write_text(markdown, encoding="utf-8")
    if args.summary_file:
        with Path(args.summary_file).open("a", encoding="utf-8") as handle:
            handle.write(markdown)
    print(markdown)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    mode = args.mode or ("surface" if args.surface_only else "capability")
    checks: list[Check] = []
    if mode == "offline":
        checks.append(Check("offline", "SKIP", "network disabled", required=False))
    else:
        client = Client(
            args.base_url,
            edge_token=args.hf_space_token,
            app_token=args.bearer_token,
            timeout=args.request_timeout,
        )
        providers = _surface_checks(client, args, checks)
        if mode == "capability":
            _capability_checks(client, args, checks, providers)
    _write_reports(args, mode, checks)
    return 1 if any(item.required and item.outcome == "FAIL" for item in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
