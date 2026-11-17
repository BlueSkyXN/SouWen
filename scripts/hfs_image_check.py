#!/usr/bin/env python3
"""Deploy-time verification for the image the HFS Space actually builds.

``cloud/hfs/Dockerfile`` is not the root ``Dockerfile``: it clones the source
itself from ``ARG SOUWEN_REF`` and runs the root ``entrypoint.sh``. The census
workflow proves the root image works; this script proves the Space image does,
without deploying anything.

It runs *inside* the container (the checkout is ``/app``), so every check
exercises the same bytes the Space would run:

``image``     build identity: selected SHA vs ``/app/runtime.source.sha`` vs
              ``git rev-parse HEAD`` in ``/app`` vs the image revision label.
``http``      ``/healthz``, ``/sources``, a real ``/search`` and a real
              ``/fetch`` that must return a usable body.
``mcp``       the official SDK: initialize -> tools/list -> tools/call on both
              tools. HTTP 200 or a correct tool name alone is not a pass.
``auth``      a password is configured: no credential / wrong Bearer / wrong
              custom header are 401 on all three entries, the right one works.
``authopen``  the effective password is None: all three entries fail closed.
``warp``      real WARP exit over the container's SOCKS5 proxy, then the
              production browser path explicitly through that proxy.

Required checks fail the run (exit 1). This is deliberately unlike
``scripts/census.py``, which records data and always exits 0: a deploy-time
check that prints FAILED and returns success is how a broken image ships.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts._functional_common import CheckSkipped, ResultRecorder, run_check

MODES = ("image", "http", "mcp", "mcpproxy", "auth", "authopen", "browser", "warp", "usque-forced")

# Frozen smoke inputs, taken from scripts/census/queries.json. Chosen before the
# first run and not swapped afterwards: paper passed 10/10 on both census legs,
# and the Wikipedia article is in the frozen static fetch set.
SMOKE_SEARCH_DOMAIN = "paper"
SMOKE_SEARCH_QUERY = "retrieval augmented generation"
SMOKE_SEARCH_LIMIT = 3
SMOKE_FETCH_URL = "https://en.wikipedia.org/wiki/Web_scraping"
MIN_FETCH_CHARS = 500

WARP_SOCKS_PROXY = "socks5://127.0.0.1:1080"
WARP_TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
BROWSER_PROBE_URL = "https://example.com/"
MIN_BROWSER_CHARS = 50

VERIFICATION_MARKERS = (
    "just a moment",
    "verify you are human",
    "checking your browser",
    "captcha",
    "are you a robot",
    "access denied",
    "attention required",
    "request blocked",
    "enable javascript and cookies",
    "permission denied | api",
    "sign in to continue",
    "log in to continue",
    "403 forbidden",
    "404 not found",
)

WRONG_BEARER = "not-the-configured-password"
WRONG_CUSTOM = "not-the-configured-password-either"
OPEN_PROBE_TOKEN = "any-arbitrary-token"

# A rejected credential must be 401/403. An accepted one only has to stop being
# rejected: /search and /fetch can still fail upstream (502/504) after the
# credential check passed, and that is a source problem, not an auth problem.
ACCEPTED = "accepted"
_UNAUTHORIZED = frozenset({401, 403})


class ProbeError(RuntimeError):
    """A probe could not be completed; recorded as a failed check.

    ``details`` carries the probe's own evidence (attempt history, manager
    state, judgements) into the failed record — without it a failure only
    keeps a traceback and the WARP leg cannot be classified from the report.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


def status_ok(status: int, expected: int | str) -> bool:
    if expected == ACCEPTED:
        return status not in _UNAUTHORIZED
    return status == expected


# ---------------------------------------------------------------- HTTP helpers


def http_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> tuple[int, Any]:
    body = None
    request_headers = {"Accept": "application/json", "User-Agent": "SouWen-HfsCheck/1"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _parse_json(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _parse_json(exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProbeError(f"request failed: {type(exc).__name__}") from exc


def _parse_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _auth_headers(token: str | None, *, custom: bool = False) -> dict[str, str]:
    if not token:
        return {}
    if custom:
        return {"X-SouWen-Token": token}
    return {"Authorization": f"Bearer {token}"}


def is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def usable_search_results(payload: Any) -> tuple[int, int]:
    """Return (usable, total): usable means non-empty title and an http(s) URL."""

    items = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return 0, 0
    usable = sum(
        1
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("title"), str)
        and item["title"].strip()
        and is_http_url(item.get("url"))
    )
    return usable, len(items)


def usable_fetch_body(payload: Any) -> tuple[bool, str]:
    """Judge one /fetch payload: real content, not an interstitial page."""

    if not isinstance(payload, dict):
        return False, "payload is not an object"
    content = payload.get("content")
    if not isinstance(content, str):
        return False, "content is not a string"
    stripped = content.strip()
    if len(stripped) < MIN_FETCH_CHARS:
        return False, f"content too short: {len(stripped)} chars"
    haystack = f"{payload.get('title') or ''}\n{stripped[:4000]}".lower()
    for marker in VERIFICATION_MARKERS:
        if marker in haystack:
            return False, f"interstitial marker: {marker}"
    return True, f"{len(stripped)} chars"


def _fetch_payload(url: str = SMOKE_FETCH_URL, max_chars: int = 200_000) -> dict[str, Any]:
    return {"url": url, "max_chars": max_chars}


def with_one_retry(probe: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    """Run ``probe`` once, retry at most once, and keep the first failure."""

    failures: list[str] = []
    for attempt in (1, 2):
        try:
            return probe(), {"attempts": attempt, "first_failure": failures[:1]}
        except ProbeError as exc:
            failures.append(f"attempt {attempt}: {exc}")
    raise ProbeError("; ".join(failures))


async def with_one_retry_async(probe: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    """Awaiting variant of :func:`with_one_retry` for checks already in a loop."""

    failures: list[str] = []
    for attempt in (1, 2):
        try:
            return await probe(), {"attempts": attempt, "first_failure": failures[:1]}
        except ProbeError as exc:
            failures.append(f"attempt {attempt}: {exc}")
    raise ProbeError("; ".join(failures))


def _run_checks(recorder: ResultRecorder, checks: list[tuple[str, Any, float]]) -> None:
    """Run every check in order, awaiting each one, and let a failure stand."""

    async def runner() -> None:
        for name, check, timeout in checks:
            await run_check(recorder, name, check, timeout=timeout)

    asyncio.run(runner())


# ---------------------------------------------------------------- image mode


def _run_git(args: list[str], cwd: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60
    )
    if completed.returncode != 0:
        raise ProbeError(f"git {' '.join(args)} failed: {completed.stderr.strip()[:200]}")
    return completed.stdout.strip()


def _runtime_identity() -> dict[str, Any]:
    import souwen

    from souwen.common_runtime.observability import get_source_sha

    return {
        "version": getattr(souwen, "__version__", None),
        "package_path": str(Path(souwen.__file__).resolve()),
        "source_sha": get_source_sha(),
        "source_sha_file_env": os.environ.get("SOUWEN_SOURCE_SHA_FILE"),
    }


def check_image(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    expected = (args.expected_sha or "").strip().lower()
    if not expected:
        raise SystemExit("--expected-sha is required for --mode image")

    def identity() -> tuple[str, dict[str, Any]]:
        runtime = _runtime_identity()
        sha_file = Path(os.environ.get("SOUWEN_SOURCE_SHA_FILE") or "/app/runtime.source.sha")
        file_value = (
            sha_file.read_text(encoding="utf-8").strip().lower() if sha_file.is_file() else ""
        )
        head_value = _run_git(["rev-parse", "HEAD"], "/app").lower()
        details = {
            "expected_sha": expected,
            "runtime_source_sha_file": file_value or "(missing)",
            "checkout_head": head_value,
            "resolved_source_sha": runtime["source_sha"],
            "souwens_version": runtime["version"],
            "package_path": runtime["package_path"],
            "source_sha_file_env": runtime["source_sha_file_env"],
        }
        mismatches = [
            name
            for name, value in (
                ("runtime.source.sha", file_value),
                ("checkout HEAD", head_value),
                ("get_source_sha()", (runtime["source_sha"] or "").lower()),
            )
            if value != expected
        ]
        if mismatches:
            raise ProbeError(f"identity mismatch: {', '.join(mismatches)}")
        return f"source identity matches {expected}", details

    def entrypoint() -> tuple[str, dict[str, Any]]:
        path = Path("/usr/local/bin/entrypoint.sh")
        if not path.is_file():
            raise ProbeError("/usr/local/bin/entrypoint.sh missing")
        text = path.read_text(encoding="utf-8", errors="replace")
        first_line = text.splitlines()[0] if text else ""
        details = {
            "path": str(path),
            "executable": os.access(path, os.X_OK),
            "shebang": first_line,
            "runs_souwen_serve": "souwen serve" in text,
        }
        if not details["executable"]:
            raise ProbeError("entrypoint is not executable")
        if not first_line.startswith("#!"):
            raise ProbeError("entrypoint has no shebang")
        if not details["runs_souwen_serve"]:
            raise ProbeError("entrypoint does not start souwen serve")
        return "entrypoint present, executable and starts souwen serve", details

    def revision_label() -> tuple[str, dict[str, Any]]:
        label = (args.image_revision or "").strip().lower()
        details = {"image_revision_label": label or "(not supplied)"}
        if not label:
            raise CheckSkipped("image revision label was not supplied by the caller")
        if label != expected:
            raise ProbeError(f"image revision label {label} != expected {expected}")
        return f"image revision label matches {expected}", details

    _run_checks(
        recorder,
        [
            ("image.identity", identity, 120),
            ("image.entrypoint", entrypoint, 60),
            ("image.revision_label", revision_label, 30),
        ],
    )


# ---------------------------------------------------------------- http mode


def check_http(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    base = args.base_url.rstrip("/")
    headers = _auth_headers(args.password)

    def healthz() -> tuple[str, dict[str, Any]]:
        status, payload = http_request(f"{base}/healthz", headers=headers, timeout=30)
        details = {"http_status": status, "payload": payload}
        if status != 200:
            raise ProbeError(f"/healthz returned {status}")
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise ProbeError("/healthz payload is not ok")
        return f"/healthz ok, version={payload.get('version')}", details

    def sources() -> tuple[str, dict[str, Any]]:
        status, payload = http_request(f"{base}/sources", headers=headers, timeout=60)
        items = payload.get("sources") if isinstance(payload, dict) else None
        if status != 200:
            raise ProbeError(f"/sources returned {status}")
        if not isinstance(items, list) or not items:
            raise ProbeError("/sources returned no sources")
        if not all(isinstance(item, dict) and isinstance(item.get("kind"), str) for item in items):
            raise ProbeError("/sources entries are missing kind")
        ids = sorted(str(item.get("id")) for item in items)
        details = {"http_status": status, "source_count": len(ids), "source_ids": ids}
        return f"{len(ids)} sources listed", details

    def search() -> tuple[str, dict[str, Any]]:
        def probe() -> tuple[int, Any]:
            return http_request(
                f"{base}/search",
                method="POST",
                payload={
                    "query": SMOKE_SEARCH_QUERY,
                    "domain": SMOKE_SEARCH_DOMAIN,
                    "limit": SMOKE_SEARCH_LIMIT,
                },
                headers=headers,
                timeout=180,
            )

        (status, payload), retry = with_one_retry(probe)
        usable, total = usable_search_results(payload)
        details = {
            "http_status": status,
            "usable_results": usable,
            "total_results": total,
            "domain": SMOKE_SEARCH_DOMAIN,
            "limit": SMOKE_SEARCH_LIMIT,
            "sources": payload.get("sources") if isinstance(payload, dict) else None,
            "urls": [item.get("url") for item in (payload or {}).get("results") or []]
            if isinstance(payload, dict)
            else None,
            **retry,
        }
        if status != 200:
            raise ProbeError(f"/search returned {status}: {(payload or {}).get('detail')}")
        if total > SMOKE_SEARCH_LIMIT:
            raise ProbeError(f"/search returned {total} items for limit={SMOKE_SEARCH_LIMIT}")
        if usable < SMOKE_SEARCH_LIMIT:
            raise ProbeError(f"/search returned {usable}/{SMOKE_SEARCH_LIMIT} usable results")
        return f"{usable} usable results for limit={SMOKE_SEARCH_LIMIT}", details

    def fetch() -> tuple[str, dict[str, Any]]:
        def probe() -> tuple[int, Any]:
            return http_request(
                f"{base}/fetch",
                method="POST",
                payload=_fetch_payload(),
                headers=headers,
                timeout=180,
            )

        (status, payload), retry = with_one_retry(probe)
        ok, reason = usable_fetch_body(payload)
        details = {
            "http_status": status,
            "url": SMOKE_FETCH_URL,
            "judgement": reason,
            "title": (payload or {}).get("title") if isinstance(payload, dict) else None,
            "total_chars": (payload or {}).get("total_chars")
            if isinstance(payload, dict)
            else None,
            "egress": (payload or {}).get("egress") if isinstance(payload, dict) else None,
            "next_start": (payload or {}).get("next_start") if isinstance(payload, dict) else None,
            "sources": (payload or {}).get("sources") if isinstance(payload, dict) else None,
            **retry,
        }
        if status != 200:
            raise ProbeError(f"/fetch returned {status}: {(payload or {}).get('detail')}")
        if not ok:
            raise ProbeError(f"/fetch body rejected: {reason}")
        return f"{reason} via egress={details['egress']}", details

    _run_checks(
        recorder,
        [
            ("http.healthz", healthz, 60),
            ("http.sources", sources, 90),
            ("http.search", search, 400),
            ("http.fetch", fetch, 400),
        ],
    )


# ---------------------------------------------------------------- mcp mode


async def _mcp_call(args: argparse.Namespace, action: Any) -> Any:
    """Run one action inside a real SDK session: initialize, then the action."""

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = args.mcp_url or f"{args.base_url.rstrip('/')}/mcp"
    headers = _auth_headers(args.password)

    async with streamablehttp_client(url, headers=headers, timeout=120) as (
        read_stream,
        write_stream,
        _session_id,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await action(session)


def _tool_text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def _is_numbered_result(line: str) -> bool:
    head, separator, rest = line.partition(". ")
    return bool(separator) and head.isdigit() and bool(rest.strip())


async def _mcp_tools_probe(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    url = args.mcp_url or f"{args.base_url.rstrip('/')}/mcp"
    result = await _mcp_call(args, lambda session: session.list_tools())
    names = sorted(tool.name for tool in result.tools)
    details = {"url": url, "tools": names}
    if names != ["fetch", "search"]:
        raise ProbeError(f"tools are {names}, expected ['fetch', 'search']")
    return "tools are exactly search and fetch", details


async def _mcp_search_probe(
    args: argparse.Namespace, *, limit: int, min_results: int
) -> tuple[str, dict[str, Any]]:
    result = await _mcp_call(
        args,
        lambda session: session.call_tool(
            "search",
            {
                "query": SMOKE_SEARCH_QUERY,
                "domain": SMOKE_SEARCH_DOMAIN,
                "limit": limit,
            },
        ),
    )
    text = _tool_text(result)
    numbered = [line for line in text.splitlines() if _is_numbered_result(line)]
    details = {
        "is_error": bool(getattr(result, "isError", False)),
        "numbered_results": len(numbered),
        "limit": limit,
        "text_head": text[:400],
    }
    if details["is_error"]:
        raise ProbeError(f"search tool returned an error: {text[:200]}")
    if len(numbered) < min_results:
        raise ProbeError(f"search tool returned {len(numbered)} results")
    return f"{len(numbered)} numbered results through tools/call", details


async def _mcp_fetch_probe(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    result = await _mcp_call(
        args,
        lambda session: session.call_tool("fetch", _fetch_payload()),
    )
    text = _tool_text(result)
    header, _separator, body = text.partition("\n")
    stripped = body.strip()
    details = {
        "is_error": bool(getattr(result, "isError", False)),
        "header": header[:300],
        "body_chars": len(stripped),
    }
    if details["is_error"]:
        raise ProbeError(f"fetch tool returned an error: {text[:200]}")
    if "egress:" not in header:
        raise ProbeError("fetch tool header does not report the egress level")
    if len(stripped) < MIN_FETCH_CHARS:
        raise ProbeError(f"fetch tool body is {len(stripped)} chars")
    haystack = stripped[:4000].lower()
    for marker in VERIFICATION_MARKERS:
        if marker in haystack:
            raise ProbeError(f"fetch tool body is an interstitial: {marker}")
    return f"{len(stripped)} chars through tools/call", details


def check_mcp(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    _run_checks(
        recorder,
        [
            ("mcp.tools_list", lambda: _mcp_tools_probe(args), 200),
            (
                "mcp.call_search",
                lambda: _mcp_search_probe(
                    args, limit=SMOKE_SEARCH_LIMIT, min_results=SMOKE_SEARCH_LIMIT
                ),
                240,
            ),
            ("mcp.call_fetch", lambda: _mcp_fetch_probe(args), 240),
        ],
    )


# ------------------------------------------------- mcp reverse-proxy host mode


async def _mcp_raw_post(
    url: str, headers: dict[str, str], timeout: float = 30.0
) -> tuple[int, str]:
    """One raw initialize POST. Returns (status, body head). No SDK session.

    Used only for negative expectations (421/403) — the handshake there fails
    before any protocol exchange, so raw status checks are the exact behavior
    under test.
    """

    import httpx

    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "hfs-proxy-check", "version": "0"},
            },
        }
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, content=body, headers=headers)
        return response.status_code, response.text[:200]


async def _mcp_proxy_handshake_probe(
    args: argparse.Namespace,
) -> tuple[str, dict[str, Any]]:
    """Real MCP handshake with an explicit reverse-proxy Host header.

    TCP still targets the container loopback (the probe runs against a local
    container); the HTTP Host header carries a deployment-shaped domain. The
    container under test must be started with SPACE_HOST set to that domain
    (mirroring the HF platform variable), so the transport-security allowlist
    resolves to loopback + that exact host. Asserts a full handshake with the
    two-tool list — 406/421/protocol errors fail the check.
    """

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    base = args.base_url.rstrip("/")
    url = f"{base}/mcp"
    probe_host = args.proxy_host
    headers = dict(_auth_headers(args.password))
    headers["Host"] = probe_host
    headers["Accept"] = "application/json, text/event-stream"

    tools: list[str] = []
    async with streamablehttp_client(url, headers=headers, timeout=120) as (
        read_stream,
        write_stream,
        _session_id,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = sorted(tool.name for tool in listed.tools)
    if tools != ["fetch", "search"]:
        raise ProbeError(f"reverse-proxy handshake saw tools {tools}")
    return (
        f"real handshake via reverse-proxy Host {probe_host}; tools exactly search/fetch",
        {"proxy_host": probe_host, "tools": tools},
    )


async def _mcp_proxy_denied_host_probe(
    args: argparse.Namespace,
) -> tuple[str, dict[str, Any]]:
    status, body = await _mcp_raw_post(
        f"{args.base_url.rstrip('/')}/mcp",
        {
            "Host": args.denied_host,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **_auth_headers(args.password),
        },
    )
    details = {"denied_host": args.denied_host, "status": status, "body_head": body[:80]}
    if status != 421:
        raise ProbeError(
            f"unlisted Host {args.denied_host} must be rejected with 421, got {status}"
        )
    return f"unlisted Host {args.denied_host} rejected with 421", details


async def _mcp_proxy_denied_origin_probe(
    args: argparse.Namespace,
) -> tuple[str, dict[str, Any]]:
    status, body = await _mcp_raw_post(
        f"{args.base_url.rstrip('/')}/mcp",
        {
            "Host": args.proxy_host,
            "Origin": "https://origin-not-allowed.example.com",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **_auth_headers(args.password),
        },
    )
    details = {
        "proxy_host": args.proxy_host,
        "denied_origin": "https://origin-not-allowed.example.com",
        "status": status,
        "body_head": body[:80],
    }
    if status != 403:
        raise ProbeError(
            f"unlisted Origin must be rejected with 403 (Host {args.proxy_host} allowed), got {status}"
        )
    return "unlisted Origin rejected with 403", details


def check_mcp_proxy(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    _run_checks(
        recorder,
        [
            (
                "mcpproxy.handshake",
                lambda: _mcp_proxy_handshake_probe(args),
                240,
            ),
            ("mcpproxy.denied_host", lambda: _mcp_proxy_denied_host_probe(args), 60),
            ("mcpproxy.denied_origin", lambda: _mcp_proxy_denied_origin_probe(args), 60),
        ],
    )


# ---------------------------------------------------------------- auth modes


def _mcp_initialize_status(base: str, headers: dict[str, str], timeout: float = 60.0) -> int:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "hfs-image-check", "version": "1"},
        },
    }
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "SouWen-HfsCheck/1",
    }
    request_headers.update(headers)
    request = urllib.request.Request(
        f"{base}/mcp",
        data=json.dumps(body).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProbeError(f"/mcp probe failed: {type(exc).__name__}") from exc


def _entry_status(base: str, entry: str, headers: dict[str, str], timeout: float = 180.0) -> int:
    if entry == "mcp":
        return _mcp_initialize_status(base, headers)
    if entry == "search":
        status, _payload = http_request(
            f"{base}/search",
            method="POST",
            payload={"query": SMOKE_SEARCH_QUERY, "domain": SMOKE_SEARCH_DOMAIN, "limit": 1},
            headers=headers,
            timeout=timeout,
        )
        return status
    status, _payload = http_request(
        f"{base}/fetch",
        method="POST",
        payload=_fetch_payload(max_chars=20_000),
        headers=headers,
        timeout=timeout,
    )
    return status


def _auth_matrix(
    base: str, *, entry: str, cases: list[tuple[str, dict[str, str], int | str]]
) -> tuple[str, dict[str, Any]]:
    observed: dict[str, int] = {}
    for name, headers, expected in cases:
        status = _entry_status(base, entry, headers)
        observed[name] = status
        if not status_ok(status, expected):
            raise ProbeError(f"{entry} {name}: {status}, expected {expected}")
    return f"{entry}: {len(observed)} credential cases as expected", {"observed": observed}


def _container_password_state() -> tuple[str | None, str | None]:
    """Read the container's own view of the user password, not the caller's."""

    from souwen.config import get_config

    cfg = get_config()
    return cfg.user_password, cfg.effective_user_password


def check_auth(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    base = args.base_url.rstrip("/")
    if not args.password:
        raise SystemExit("--password is required for --mode auth")
    good = _auth_headers(args.password)

    def configured() -> tuple[str, dict[str, Any]]:
        raw, effective = _container_password_state()
        details = {
            "user_password_is_none": raw is None,
            "effective_password_matches_argument": effective == args.password,
        }
        if raw is None:
            raise ProbeError("container has no configured password; run --mode authopen")
        if effective != args.password:
            raise ProbeError("container password does not match --password")
        return "container has the expected password configured", details

    def matrix(entry: str) -> Any:
        def probe() -> tuple[str, dict[str, Any]]:
            return _auth_matrix(
                base,
                entry=entry,
                cases=[
                    ("no_credential", {}, 401),
                    ("wrong_bearer", _auth_headers(WRONG_BEARER), 401),
                    ("wrong_custom_token", _auth_headers(WRONG_CUSTOM, custom=True), 401),
                    ("correct_password", good, ACCEPTED),
                ],
            )

        return probe

    _run_checks(
        recorder,
        [
            ("auth.configured", configured, 60),
            ("auth.search", matrix("search"), 400),
            ("auth.fetch", matrix("fetch"), 400),
            ("auth.mcp", matrix("mcp"), 300),
        ],
    )


def check_authopen(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    """``user_password is None`` must fail closed on all three entries."""

    base = args.base_url.rstrip("/")

    def password_is_none() -> tuple[str, dict[str, Any]]:
        raw, effective = _container_password_state()
        # 只输出布尔状态：口令原文绝不能进异常消息、报告或 traceback。
        details = {
            "user_password_configured": raw is not None,
            "effective_password_configured": effective is not None,
        }
        if raw is not None or effective is not None:
            raise ProbeError(
                "user_password is configured; expected None for the fail-closed "
                "matrix; run --mode auth instead"
            )
        return "user_password is None and the effective password is unset", details

    def matrix(entry: str) -> Any:
        def probe() -> tuple[str, dict[str, Any]]:
            return _auth_matrix(
                base,
                entry=entry,
                cases=[
                    ("no_credential", {}, 401),
                    ("arbitrary_bearer", _auth_headers(OPEN_PROBE_TOKEN), 401),
                    ("arbitrary_custom_token", _auth_headers(OPEN_PROBE_TOKEN, custom=True), 401),
                ],
            )

        return probe

    _run_checks(
        recorder,
        [
            ("authopen.password_is_none", password_is_none, 60),
            ("authopen.search", matrix("search"), 300),
            ("authopen.fetch", matrix("fetch"), 300),
            ("authopen.mcp", matrix("mcp"), 300),
        ],
    )


# ---------------------------------------------------------------- browser mode


async def _browser_fetch(url: str, *, proxy: str | None) -> Any:
    from souwen.common_runtime.provider_support.browser_fetch import fetch_page_content

    return await fetch_page_content(
        url,
        max_code_points=4000,
        timeout_seconds=90.0,
        proxy=proxy,
    )


async def browser_probe(url: str, *, proxy: str | None) -> dict[str, Any]:
    """Drive the production browser path once (one retry) and judge the body."""

    from souwen.common_runtime.provider_support.browser_fetch import (
        BrowserAcquisitionError,
        chromium_available,
    )

    async def probe() -> dict[str, Any]:
        try:
            outcome = await _browser_fetch(url, proxy=proxy)
        except BrowserAcquisitionError as exc:
            raise ProbeError(f"browser acquisition failed: {exc.code}") from None
        body = outcome.content.strip()
        if len(body) < MIN_BROWSER_CHARS:
            raise ProbeError(f"browser body too short: {len(body)} chars")
        return {
            "url": url,
            "proxy": proxy,
            "final_url": outcome.final_url,
            "title": outcome.title,
            "chars": len(body),
        }

    details, retry = await with_one_retry_async(probe)
    details.update(retry)
    details["chromium_available"] = chromium_available()
    return details


def check_browser(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    def availability() -> tuple[str, dict[str, Any]]:
        from souwen.common_runtime.provider_support.browser_fetch import chromium_available

        available = chromium_available()
        if not available:
            raise ProbeError("Chromium is not installed in this image")
        return "Chromium is installed", {"chromium_available": available}

    async def render() -> tuple[str, dict[str, Any]]:
        details = await browser_probe(BROWSER_PROBE_URL, proxy=None)
        return f"rendered {details['chars']} chars through fetch_page_content", details

    _run_checks(
        recorder,
        [
            ("browser.chromium_available", availability, 60),
            ("browser.fetch_page_content", render, 300),
        ],
    )


# ---------------------------------------------------------------- warp mode


def _trace_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


# manager 在后台任务里启动 WARP，状态文件是稍后才落盘的。探针首次读取可能
# 早于写入，这里给它一点等待时间；测试把它设为 0 以免真的睡。
WARP_STATE_WAIT_SECONDS = 30.0

IMPLEMENTATION_ERROR_MARKERS = (
    "AttributeError",
    "TypeError",
    "KeyError",
    "IndexError",
    "ImportError",
    "NameError",
    "NotImplementedError",
    # usque 的交互式提示：服务进程没有终端，读到 EOF 就必然失败，每次都会复现。
    # 这类失败是实现/配置缺陷，不能记成"外部注册不可用"。
    "failed to read user input",
    "user did not accept TOS",
    "Config path is required",
)


def _warp_state_file() -> Path:
    from souwen.server.warp import STATE_FILE

    return STATE_FILE


def _warp_state_details(*, wait_seconds: float = 0.0) -> dict[str, Any]:
    """Read the manager's persisted state: the actual mode, not the recommended one.

    ``WarpManager`` shares ``/run/souwen-warp.json`` with the server process, so
    this is evidence of which start method really ran — 'installed' or
    'recommended' from a capability probe is not.

    The manager starts WARP on a background task, so the file may not exist yet
    when the first probe runs. ``wait_seconds`` polls instead of reporting a
    transient "unreadable", which previously made two checks in one report
    disagree about the same state.
    """

    from souwen.server.warp import STATE_FILE, WarpState

    expected = str(STATE_FILE)
    deadline = time.monotonic() + max(wait_seconds, 0.0)
    while True:
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state = WarpState.from_dict(raw) if isinstance(raw, dict) else None
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                return {"state_file": "missing"}
            time.sleep(1)
            continue
        except Exception as exc:  # noqa: BLE001 - evidence collection must not crash a check
            return {"state_file": "unreadable", "error": f"{type(exc).__name__}: {exc}"}
        if state is None:
            return {"state_file": "unreadable", "error": "state file is not a JSON object"}
        return {
            "state_file": expected,
            "mode": state.mode,
            "status": state.status,
            "owner": state.owner,
            "ip": state.ip,
            "last_error": (state.last_error or "")[:300] or None,
            "implementation_error": any(
                marker in (state.last_error or "") for marker in IMPLEMENTATION_ERROR_MARKERS
            ),
        }


def warp_trace_direct(timeout: float = 30.0) -> dict[str, str]:
    """Read the Cloudflare trace over the container's direct egress."""

    request = urllib.request.Request(WARP_TRACE_URL, headers={"User-Agent": "SouWen-HfsCheck/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProbeError(f"direct trace failed: {type(exc).__name__}") from exc
    fields = _trace_fields(text)
    if not fields:
        raise ProbeError("direct trace response had no fields")
    return fields


def warp_trace(proxy: str, timeout: float = 30.0) -> dict[str, str]:
    """Read the Cloudflare trace through a SOCKS5 proxy; no proxy, no result."""

    import httpx

    try:
        with httpx.Client(proxy=proxy, timeout=timeout, trust_env=False) as client:
            response = client.get(WARP_TRACE_URL, headers={"User-Agent": "SouWen-HfsCheck/1"})
            response.raise_for_status()
            text = response.text
    except Exception as exc:  # noqa: BLE001 - a proxy failure is the probe result
        raise ProbeError(f"socks trace failed: {type(exc).__name__}") from exc
    fields = _trace_fields(text)
    if not fields:
        raise ProbeError("proxied trace response had no fields")
    return fields


def check_warp(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    base = args.base_url.rstrip("/")
    proxy = args.warp_proxy or WARP_SOCKS_PROXY
    attempts = args.warp_attempts
    headers = _auth_headers(args.password)

    def socks_egress() -> tuple[str, dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for attempt in range(1, attempts + 1):
            try:
                fields = warp_trace(proxy)
            except ProbeError as exc:
                history.append({"attempt": attempt, "error": str(exc)})
                time.sleep(10)
                continue
            history.append(
                {
                    "attempt": attempt,
                    "warp": fields.get("warp"),
                    "ip": fields.get("ip"),
                    "colo": fields.get("colo"),
                }
            )
            if fields.get("warp") == "on":
                return (
                    f"warp=on verified after {attempt} attempt(s)",
                    {
                        "history": history,
                        "warp_state": _warp_state_details(wait_seconds=WARP_STATE_WAIT_SECONDS),
                    },
                )
            time.sleep(10)
        raise ProbeError(
            f"warp=on not observed after {attempts} attempts: {history[-1:]}",
            details={
                "history": history,
                "warp_state": _warp_state_details(wait_seconds=WARP_STATE_WAIT_SECONDS),
            },
        )

    def exit_differs() -> tuple[str, dict[str, Any]]:
        direct = warp_trace_direct()
        proxied = warp_trace(proxy)
        details = {
            "direct_ip": direct.get("ip"),
            "proxied_ip": proxied.get("ip"),
            "proxied_warp": proxied.get("warp"),
        }
        if not proxied.get("ip"):
            raise ProbeError("proxied trace has no ip field")
        if direct.get("ip") == proxied.get("ip"):
            raise ProbeError("proxied and direct exit IP are identical")
        return "proxied exit IP differs from the direct exit IP", details

    async def browser_via_warp() -> tuple[str, dict[str, Any]]:
        details = await browser_probe(BROWSER_PROBE_URL, proxy=proxy)
        return f"browser fetched {details['chars']} chars through WARP", details

    async def mcp_after_warp() -> tuple[str, dict[str, Any]]:
        search_message, search_details = await _mcp_search_probe(args, limit=1, min_results=1)
        fetch_message, fetch_details = await _mcp_fetch_probe(args)
        details = {
            "mcp_search": search_details,
            "mcp_fetch": fetch_details,
            "warp_state": _warp_state_details(),
        }
        return f"MCP under WARP: {search_message}; {fetch_message}", details

    def http_after_warp() -> tuple[str, dict[str, Any]]:
        def probe() -> tuple[int, Any, int, Any]:
            search_status, search_payload = http_request(
                f"{base}/search",
                method="POST",
                payload={"query": SMOKE_SEARCH_QUERY, "domain": SMOKE_SEARCH_DOMAIN, "limit": 1},
                headers=headers,
                timeout=180,
            )
            fetch_status, fetch_payload = http_request(
                f"{base}/fetch",
                method="POST",
                payload=_fetch_payload(),
                headers=headers,
                timeout=180,
            )
            return search_status, search_payload, fetch_status, fetch_payload

        (status, search_payload, fetch_status, fetch_payload), retry = with_one_retry(probe)
        search_usable, search_total = usable_search_results(search_payload)
        fetch_ok, fetch_reason = usable_fetch_body(fetch_payload)
        details = {
            "search_status": status,
            "search_usable": search_usable,
            "search_total": search_total,
            "search_sources": (search_payload or {}).get("sources")
            if isinstance(search_payload, dict)
            else None,
            "fetch_status": fetch_status,
            "fetch_judgement": fetch_reason,
            "fetch_egress": (fetch_payload or {}).get("egress")
            if isinstance(fetch_payload, dict)
            else None,
            "warp_state": _warp_state_details(),
            **retry,
        }
        if status != 200:
            raise ProbeError(f"/search returned {status} under WARP")
        if search_total > 1:
            raise ProbeError(f"/search returned {search_total} items for limit=1 under WARP")
        if search_usable < 1:
            raise ProbeError(
                f"/search returned {search_usable}/{search_total} usable results under WARP",
                details=details,
            )
        if fetch_status != 200:
            raise ProbeError(f"/fetch returned {fetch_status} under WARP", details=details)
        if not fetch_ok:
            raise ProbeError(f"/fetch body rejected under WARP: {fetch_reason}", details=details)
        return (
            f"/search and /fetch work under WARP (fetch egress={details['fetch_egress']})",
            details,
        )

    def actual_mode() -> tuple[str, dict[str, Any]]:
        """Record which start method really ran — auto may have fallen back.

        The capability probe's recommendation is not usage evidence: usque was
        recommended for several rounds while `_start_usque` was missing and the
        proxy only came up after auto fell back to wireproxy. This check makes
        the actual mode a required result instead of a detail nobody reads.
        """

        state = _warp_state_details(wait_seconds=WARP_STATE_WAIT_SECONDS)
        if state.get("state_file") == "missing":
            raise ProbeError(
                "WARP manager never wrote its state file; the actual mode is unproven",
                details=state,
            )
        if state.get("status") != "enabled":
            raise ProbeError(
                f"WARP manager state is {state.get('status')!r}, not enabled", details=state
            )
        mode = state.get("mode")
        return f"manager actually ran mode {mode!r} (status={state.get('status')})", state

    _run_checks(
        recorder,
        [
            ("warp.socks_egress", socks_egress, attempts * 40 + 120),
            ("warp.exit_differs", exit_differs, 180),
            ("warp.actual_mode", actual_mode, 90),
            ("warp.browser_via_warp", browser_via_warp, 300),
            ("warp.mcp_after_warp", mcp_after_warp, 400),
            ("warp.http_after_warp", http_after_warp, 500),
        ],
    )


# ------------------------------------------------------------- usque-forced mode


def check_usque_forced(recorder: ResultRecorder, args: argparse.Namespace) -> None:
    """Limited verification of a container started with ``WARP_MODE=usque``.

    The point is evidence, not a pass: if the usque start method really runs
    (manager mode ``usque`` and a real ``warp=on`` exit) the record says so; if
    registration or the tunnel does not come up the record says unverified with
    the manager's own error; an implementation error (AttributeError & co) is
    a defect and must fail, never masquerade as an environment problem.
    """

    proxy = args.warp_proxy or WARP_SOCKS_PROXY
    attempts = args.usque_attempts

    def mode_requested() -> tuple[str, dict[str, Any]]:
        from souwen.config import get_config

        cfg = get_config()
        details = {"warp_mode": cfg.warp_mode, "expected": "usque"}
        if cfg.warp_mode != "usque":
            raise ProbeError(f"container warp_mode is {cfg.warp_mode!r}, expected 'usque'")
        return "container was started with WARP_MODE=usque", details

    def socks_egress() -> tuple[str, dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for attempt in range(1, attempts + 1):
            try:
                fields = warp_trace(proxy)
            except ProbeError as exc:
                history.append({"attempt": attempt, "error": str(exc)})
                time.sleep(10)
                continue
            history.append(
                {
                    "attempt": attempt,
                    "warp": fields.get("warp"),
                    "ip": fields.get("ip"),
                    "colo": fields.get("colo"),
                }
            )
            if fields.get("warp") == "on":
                return (
                    f"warp=on verified after {attempt} attempt(s)",
                    {
                        "history": history,
                        "warp_state": _warp_state_details(wait_seconds=WARP_STATE_WAIT_SECONDS),
                    },
                )
            time.sleep(10)
        state = _warp_state_details(wait_seconds=WARP_STATE_WAIT_SECONDS)
        # 失败必须带上尝试历史与 manager 状态：分类器要靠它区分外部不可用与
        # 实现缺陷，缺了这两项就只能看到一条 traceback。
        raise ProbeError(
            f"warp=on not observed after {attempts} attempts under forced usque; "
            f"manager state: {state}",
            details={"history": history, "warp_state": state},
        )

    def actual_mode() -> tuple[str, dict[str, Any]]:
        # manager 在后台线程启动 WARP，状态文件要等它写；这里短暂轮询，
        # 而不是一看到文件不在就跳过——"没读到状态"不是"无需归属"。
        deadline = time.monotonic() + 60
        state = _warp_state_details()
        while state.get("state_file") != str(_warp_state_file()) and time.monotonic() < deadline:
            time.sleep(2)
            state = _warp_state_details()
        if state.get("state_file") != str(_warp_state_file()):
            raise ProbeError(
                f"WARP manager never wrote its state file; the actual mode is unproven ({state})",
                details=state,
            )
        if state.get("status") != "enabled":
            raise ProbeError(
                f"WARP manager state is {state.get('status')!r}, not enabled", details=state
            )
        if state.get("mode") != "usque":
            raise ProbeError(
                f"manager actually ran mode {state.get('mode')!r}, not usque; "
                "the recommendation alone is not usage evidence",
                details=state,
            )
        return f"manager actually ran mode usque (status={state.get('status')})", state

    async def browser_via_usque() -> tuple[str, dict[str, Any]]:
        details = await browser_probe(BROWSER_PROBE_URL, proxy=proxy)
        return f"browser fetched {details['chars']} chars through forced usque", details

    _run_checks(
        recorder,
        [
            ("usqueforced.mode_requested", mode_requested, 60),
            ("usqueforced.socks_egress", socks_egress, attempts * 40 + 120),
            ("usqueforced.actual_mode", actual_mode, 60),
            ("usqueforced.browser_via_usque", browser_via_usque, 300),
        ],
    )


# ---------------------------------------------------------------- entry point


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--base-url", default="http://127.0.0.1:49265")
    parser.add_argument("--mcp-url", default=None, help="Defaults to <base-url>/mcp")
    parser.add_argument("--password", default=None, help="Configured user password, if any")
    parser.add_argument(
        "--proxy-host",
        default="demo-space.hf.space",
        help="Deployment-shaped Host for the reverse-proxy MCP probe (mcpproxy mode); "
        "the container must be started with SPACE_HOST set to the same value",
    )
    parser.add_argument(
        "--denied-host",
        default="host-not-allowed.example.com",
        help="Host that must be rejected with 421 in the mcpproxy probe",
    )
    parser.add_argument("--expected-sha", default=None, help="Selected 40-hex source SHA")
    parser.add_argument("--image-revision", default=None, help="Image revision label value")
    parser.add_argument("--warp-proxy", default=None, help=f"Defaults to {WARP_SOCKS_PROXY}")
    parser.add_argument("--warp-attempts", type=int, default=18)
    parser.add_argument("--usque-attempts", type=int, default=12)
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--markdown-report", type=Path, default=None)
    parser.add_argument("--summary-file", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    recorder = ResultRecorder(
        script=f"hfs_image_check:{args.mode}",
        mode=args.mode,
        environment={
            "base_url": args.base_url,
            "expected_sha": args.expected_sha,
            "image_revision": args.image_revision,
        },
    )
    handlers = {
        "image": check_image,
        "http": check_http,
        "mcp": check_mcp,
        "mcpproxy": check_mcp_proxy,
        "auth": check_auth,
        "authopen": check_authopen,
        "browser": check_browser,
        "warp": check_warp,
        "usque-forced": check_usque_forced,
    }
    handlers[args.mode](recorder, args)

    recorder.write_reports(json_report=args.json_report, markdown_report=args.markdown_report)
    markdown = recorder.render_markdown()
    print(markdown)
    if args.summary_file is not None:
        with args.summary_file.open("a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    print(f"hfs_image_check {args.mode}: overall={recorder.overall.value}", file=sys.stderr)
    return recorder.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
