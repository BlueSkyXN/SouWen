#!/usr/bin/env python3
"""Post-CD report for the public Hugging Face Space.

The script intentionally uses only the Python standard library so it can run in
GitHub Actions immediately after the Space factory rebuild request.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://blueskyxn-souwen.hf.space"
USER_AGENT = "SouWen HF Space CD report/1.0"

DEFAULT_PAPER_SOURCES = [
    "openalex",
    "crossref",
    "arxiv",
    "dblp",
    "pubmed",
    "biorxiv",
]
EXTRA_ZERO_KEY_PAPER_SOURCES = [
    "semantic_scholar",
    "huggingface",
    "europepmc",
    "pmc",
    "doaj",
    "zenodo",
    "hal",
    "openaire",
    "iacr",
]
ZERO_KEY_PATENT_SOURCES = [
    "google_patents",
    "patentsview",
    "pqai",
]
ZERO_KEY_WEB_SCRAPERS = [
    "duckduckgo",
    "bing",
    "bing_cn",
    "yahoo",
    "baidu",
    "mojeek",
    "yandex",
    "brave",
    "google",
    "startpage",
]
MATRIX_HTTP_BACKENDS = ["curl_cffi", "httpx"]
DEFAULT_WARP_MODES = ["auto"]
ZERO_KEY_OPEN_SEARCH_SOURCES = [
    "reddit",
    "weibo",
    "zhihu",
    "wikipedia",
    "github",
    "stackoverflow",
    "bilibili",
    "community_cn",
    "coolapk",
    "csdn",
    "hostloc",
    "juejin",
    "linuxdo",
    "nodeseek",
    "v2ex",
    "xiaohongshu",
]
ZERO_KEY_FETCH_PROVIDER_TESTS = [
    {
        "provider": "builtin",
        "urls": ["https://example.com/"],
        "timeout": 15,
        "backend_matrix": True,
        "note": "builtin HTTP fetcher",
    },
    {
        "provider": "jina_reader",
        "urls": ["https://example.com/"],
        "timeout": 20,
        "backend_matrix": False,
        "note": "public Jina Reader endpoint; API key optional",
    },
    {
        "provider": "arxiv_fulltext",
        "urls": ["https://arxiv.org/abs/1706.03762"],
        "timeout": 35,
        "backend_matrix": False,
        "note": "arXiv HTML/PDF fulltext",
    },
    {
        "provider": "crawl4ai",
        "urls": ["https://example.com/"],
        "timeout": 30,
        "backend_matrix": False,
        "note": "zero-key but requires optional crawl4ai/browser runtime",
    },
    {
        "provider": "newspaper",
        "urls": ["https://example.com/"],
        "timeout": 20,
        "backend_matrix": True,
        "note": "zero-key but requires optional newspaper4k runtime",
    },
    {
        "provider": "readability",
        "urls": ["https://example.com/"],
        "timeout": 20,
        "backend_matrix": True,
        "note": "zero-key but requires optional readability-lxml runtime",
    },
    {
        "provider": "site_crawler",
        "urls": ["https://example.com/"],
        "timeout": 20,
        "backend_matrix": True,
        "note": "single-page site crawler path through /fetch",
    },
    {
        "provider": "deepwiki",
        "urls": ["https://deepwiki.com/BlueSkyXN/SouWen"],
        "timeout": 45,
        "backend_matrix": True,
        "note": "DeepWiki GitHub repo docs fetch",
    },
    {
        "provider": "wayback",
        "urls": ["https://example.com/"],
        "timeout": 30,
        "backend_matrix": True,
        "note": "Wayback fetch provider, separate from CDX/check endpoints",
    },
]
ZERO_KEY_FETCH_SKIPPED = [
    {
        "provider": "mcp",
        "reason": "requires an external MCP fetch server URL (SOUWEN_MCP_SERVER_URL)",
    },
]
EXCLUDED_REQUIRED_KEY_SEARCH_SOURCES = [
    "core",
    "zotero",
    "ieee_xplore",
    "epo_ops",
    "uspto_odp",
    "the_lens",
    "cnipa",
    "patsnap",
    "serpapi",
    "brave_api",
    "serper",
    "scrapingdog",
    "metaso",
    "tavily",
    "exa",
    "perplexity",
    "firecrawl",
    "linkup",
    "xcrawl",
    "zhipuai",
    "aliyun_iqs",
    "twitter",
    "facebook",
    "youtube",
    "feishu_drive",
]
EXCLUDED_SELF_HOSTED_SEARCH_SOURCES = ["searxng", "whoogle", "websurfx"]
EXCLUDED_NO_PUBLIC_ENDPOINT_SOURCES = ["unpaywall", "duckduckgo_news"]
EXCLUDED_REQUIRED_KEY_FETCH_PROVIDERS = [
    "tavily",
    "firecrawl",
    "xcrawl",
    "exa",
    "scrapfly",
    "diffbot",
    "scrapingbee",
    "zenrows",
    "scraperapi",
    "apify",
    "cloudflare",
]
EXCLUDED_REQUIRED_KEY_ROUTE_APIS = [
    "/api/v1/youtube/trending",
    "/api/v1/youtube/video/{video_id}",
    "/api/v1/youtube/transcript/{video_id}",
]
EXCLUDED_LLM_ROUTE_APIS = [
    "/api/v1/summarize",
    "/api/v1/fetch/summarize",
]


class SmokeError(RuntimeError):
    """Raised when a request cannot be evaluated."""


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    expected_version: str | None
    request_timeout: float
    bearer_token: str | None = None
    warp_modes: list[str] = field(default_factory=lambda: list(DEFAULT_WARP_MODES))
    require_admin: bool = True
    require_openapi: bool = True
    require_warp: bool = True
    full_matrix: bool = True
    min_default_paper_no_warp: int = 4
    min_default_paper_warp: int = 5
    min_best_web_engines: int = 1
    surface_only: bool = False


@dataclass(frozen=True)
class ResponseData:
    status: int
    data: Any
    elapsed: float


@dataclass(frozen=True)
class TextResponseData:
    status: int
    text: str
    headers: dict[str, str]
    elapsed: float


@dataclass
class ProbeResult:
    section: str
    name: str
    outcome: str
    detail: str
    required: bool = False
    elapsed: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.outcome in {"pass", "warn", "skip"}


@dataclass
class RunState:
    original_backend: str | None = None
    original_warp_status: dict[str, Any] | None = None
    available_warp_modes: dict[str, bool] = field(default_factory=dict)
    observed_warp_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    admin_available: bool = False
    backend_snapshot_ok: bool = False
    warp_snapshot_ok: bool = False
    warp_available: bool = False


def normalize_base_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("base URL cannot be empty")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


class ApiClient:
    def __init__(self, config: SmokeConfig):
        self.config = config

    def _request_raw(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        auth: bool = False,
        timeout: float | None = None,
    ) -> tuple[int, bytes, dict[str, str], float]:
        url = urljoin(f"{self.config.base_url}/", path.lstrip("/"))
        if params:
            clean_params = {
                k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()
            }
            url = f"{url}?{urlencode(clean_params)}"

        payload = None
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"

        started = time.monotonic()
        request = Request(url, data=payload, headers=headers, method=method.upper())
        try:
            with urlopen(  # noqa: S310 - the target is controlled by workflow configuration
                request,
                timeout=timeout or self.config.request_timeout,
            ) as response:
                status = int(response.status)
                raw = response.read()
                response_headers = dict(response.headers.items())
        except HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
            response_headers = dict(exc.headers.items())
        except (TimeoutError, URLError, OSError) as exc:
            raise SmokeError(f"{method.upper()} {path} failed: {exc}") from exc

        elapsed = time.monotonic() - started
        return status, raw, response_headers, elapsed

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        auth: bool = False,
        timeout: float | None = None,
    ) -> ResponseData:
        status, raw, _headers, elapsed = self._request_raw(
            method,
            path,
            params=params,
            body=body,
            auth=auth,
            timeout=timeout,
        )
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - report endpoint behavior in CI
            preview = raw[:240].decode("utf-8", errors="replace")
            raise SmokeError(
                f"{method.upper()} {path} returned non-JSON status={status} body={preview!r}"
            ) from exc
        if not isinstance(decoded, (dict, list)):
            raise SmokeError(
                f"{method.upper()} {path} returned {type(decoded).__name__}, "
                "expected JSON object or array"
            )
        return ResponseData(status=status, data=decoded, elapsed=elapsed)

    def request_text(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        auth: bool = False,
        timeout: float | None = None,
    ) -> TextResponseData:
        status, raw, headers, elapsed = self._request_raw(
            method,
            path,
            params=params,
            body=body,
            auth=auth,
            timeout=timeout,
        )
        text = raw.decode("utf-8", errors="replace")
        return TextResponseData(status=status, text=text, headers=headers, elapsed=elapsed)

    def get(self, path: str, **kwargs: Any) -> ResponseData:
        return self.request("GET", path, **kwargs)

    def get_text(self, path: str, **kwargs: Any) -> TextResponseData:
        return self.request_text("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> ResponseData:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> ResponseData:
        return self.request("PUT", path, **kwargs)


def pass_result(
    section: str,
    name: str,
    detail: str,
    *,
    required: bool = False,
    elapsed: float | None = None,
    meta: dict[str, Any] | None = None,
) -> ProbeResult:
    return ProbeResult(section, name, "pass", detail, required, elapsed, meta or {})


def fail_result(
    section: str,
    name: str,
    detail: str,
    *,
    required: bool = False,
    elapsed: float | None = None,
    meta: dict[str, Any] | None = None,
) -> ProbeResult:
    return ProbeResult(section, name, "fail", detail, required, elapsed, meta or {})


def warn_result(
    section: str,
    name: str,
    detail: str,
    *,
    elapsed: float | None = None,
    meta: dict[str, Any] | None = None,
) -> ProbeResult:
    return ProbeResult(section, name, "warn", detail, False, elapsed, meta or {})


def skip_result(section: str, name: str, detail: str) -> ProbeResult:
    return ProbeResult(section, name, "skip", detail, False)


def check_version(data: dict[str, Any], expected_version: str | None) -> tuple[bool, str]:
    actual = data.get("version")
    if expected_version is None:
        return True, f"version={actual!r}"
    if actual == expected_version:
        return True, f"version={actual!r}"
    return False, f"version={actual!r}, expected={expected_version!r}"


def safe_call(
    section: str,
    name: str,
    func,
    *,
    required: bool = False,
) -> ProbeResult:
    try:
        return func()
    except SmokeError as exc:
        if required:
            return fail_result(section, name, str(exc), required=True)
        return warn_result(section, name, str(exc))
    except Exception as exc:  # noqa: BLE001 - CI report should capture unexpected behavior
        if not required:
            return warn_result(section, name, f"{type(exc).__name__}: {exc}")
        return fail_result(
            section,
            name,
            f"{type(exc).__name__}: {exc}",
            required=required,
        )


def run_basic_checks(client: ApiClient, config: SmokeConfig, state: RunState) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    def _health() -> ProbeResult:
        resp = client.get("/health")
        version_ok, version_detail = check_version(resp.data, config.expected_version)
        ok = resp.status == 200 and resp.data.get("status") == "ok" and version_ok
        detail = f"status={resp.status}, health={resp.data.get('status')!r}, {version_detail}"
        return (
            pass_result("basic", "health", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("basic", "health", detail, required=True, elapsed=resp.elapsed)
        )

    def _readiness() -> ProbeResult:
        resp = client.get("/readiness")
        version_ok, version_detail = check_version(resp.data, config.expected_version)
        ok = resp.status == 200 and resp.data.get("ready") is True and version_ok
        detail = (
            f"status={resp.status}, ready={resp.data.get('ready')!r}, "
            f"error={resp.data.get('error')!r}, {version_detail}"
        )
        return (
            pass_result("basic", "readiness", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("basic", "readiness", detail, required=True, elapsed=resp.elapsed)
        )

    def _openapi() -> ProbeResult:
        if not config.require_openapi:
            return skip_result("basic", "openapi", "not required")
        resp = client.get("/openapi.json")
        info = resp.data.get("info") if isinstance(resp.data.get("info"), dict) else {}
        title = info.get("title")
        version = info.get("version")
        version_ok = config.expected_version is None or version == config.expected_version
        ok = resp.status == 200 and title == "SouWen API" and version_ok
        detail = f"status={resp.status}, title={title!r}, version={version!r}"
        return (
            pass_result("basic", "openapi", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("basic", "openapi", detail, required=True, elapsed=resp.elapsed)
        )

    def _docs() -> ProbeResult:
        if not config.require_openapi:
            return skip_result("basic", "docs", "not required")
        resp = client.get_text("/docs")
        content_type = resp.headers.get("content-type", resp.headers.get("Content-Type", ""))
        text_lower = resp.text.lower()
        ok = (
            resp.status == 200
            and "text/html" in content_type.lower()
            and ("swagger ui" in text_lower or "swagger-ui" in text_lower)
        )
        detail = f"status={resp.status}, content_type={content_type!r}, html_len={len(resp.text)}"
        return (
            pass_result("basic", "docs", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("basic", "docs", detail, required=True, elapsed=resp.elapsed)
        )

    def _panel() -> ProbeResult:
        resp = client.get_text("/panel")
        content_type = resp.headers.get("content-type", resp.headers.get("Content-Type", ""))
        text_lower = resp.text.lower()
        ok = (
            resp.status == 200
            and "text/html" in content_type.lower()
            and ('<div id="root"' in text_lower or "souwen" in text_lower)
        )
        detail = f"status={resp.status}, content_type={content_type!r}, html_len={len(resp.text)}"
        return (
            pass_result("basic", "panel", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("basic", "panel", detail, required=True, elapsed=resp.elapsed)
        )

    def _whoami() -> ProbeResult:
        resp = client.get("/api/v1/whoami", auth=True)
        role = resp.data.get("role")
        state.admin_available = resp.status == 200 and role == "admin"
        if config.require_admin:
            ok = state.admin_available
            detail = f"status={resp.status}, role={role!r}, expected='admin'"
            return (
                pass_result("basic", "whoami", detail, required=True, elapsed=resp.elapsed)
                if ok
                else fail_result("basic", "whoami", detail, required=True, elapsed=resp.elapsed)
            )
        if resp.status == 401:
            return pass_result(
                "basic",
                "whoami",
                "status=401, endpoint is protected",
                elapsed=resp.elapsed,
            )
        ok = resp.status == 200 and role in {"admin", "user", "guest"}
        detail = f"status={resp.status}, role={role!r}"
        return (
            pass_result("basic", "whoami", detail, elapsed=resp.elapsed)
            if ok
            else fail_result("basic", "whoami", detail, elapsed=resp.elapsed)
        )

    for name, func in [
        ("health", _health),
        ("readiness", _readiness),
        ("openapi", _openapi),
        ("docs", _docs),
        ("panel", _panel),
        ("whoami", _whoami),
    ]:
        results.append(safe_call("basic", name, func, required=name != "whoami"))
    return results


def run_admin_checks(client: ApiClient, config: SmokeConfig, state: RunState) -> list[ProbeResult]:
    if not state.admin_available:
        detail = "admin role is unavailable; management and mutation tests skipped"
        return [fail_result("admin", "admin-access", detail, required=config.require_admin)]

    results: list[ProbeResult] = []

    def _admin_ping() -> ProbeResult:
        resp = client.get("/api/v1/admin/ping", auth=True)
        ok = resp.status == 200 and resp.data.get("status") == "ok"
        detail = f"status={resp.status}, ping={resp.data.get('status')!r}"
        return (
            pass_result("admin", "ping", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "ping", detail, required=True, elapsed=resp.elapsed)
        )

    def _config() -> ProbeResult:
        resp = client.get("/api/v1/admin/config", auth=True)
        ok = resp.status == 200 and "default_http_backend" in resp.data
        detail = (
            f"status={resp.status}, default_http_backend={resp.data.get('default_http_backend')!r}, "
            f"warp_enabled={resp.data.get('warp_enabled')!r}"
        )
        return (
            pass_result("admin", "config", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "config", detail, required=True, elapsed=resp.elapsed)
        )

    def _http_backend_get() -> ProbeResult:
        resp = client.get("/api/v1/admin/http-backend", auth=True)
        ok = resp.status == 200 and resp.data.get("default") in {"auto", "curl_cffi", "httpx"}
        if ok:
            state.original_backend = str(resp.data.get("default"))
            state.backend_snapshot_ok = True
        detail = (
            f"status={resp.status}, default={resp.data.get('default')!r}, "
            f"curl_cffi_available={resp.data.get('curl_cffi_available')!r}"
        )
        return (
            pass_result("admin", "http-backend-get", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result(
                "admin", "http-backend-get", detail, required=True, elapsed=resp.elapsed
            )
        )

    def _warp_status() -> ProbeResult:
        resp = client.get("/api/v1/admin/warp", auth=True)
        ok = resp.status == 200 and "status" in resp.data and "available_modes" in resp.data
        if ok:
            state.original_warp_status = dict(resp.data)
            state.warp_snapshot_ok = True
        available_modes = resp.data.get("available_modes")
        if isinstance(available_modes, dict):
            state.available_warp_modes.update(
                {str(key): bool(value) for key, value in available_modes.items()}
            )
        detail = (
            f"status={resp.status}, warp_status={resp.data.get('status')!r}, "
            f"mode={resp.data.get('mode')!r}, ip={resp.data.get('ip')!r}"
        )
        return (
            pass_result("admin", "warp-status", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "warp-status", detail, required=True, elapsed=resp.elapsed)
        )

    def _warp_modes() -> ProbeResult:
        resp = client.get("/api/v1/admin/warp/modes", auth=True)
        modes = resp.data.get("modes")
        installed = []
        if isinstance(modes, list):
            installed = [m.get("id") for m in modes if isinstance(m, dict) and m.get("installed")]
            state.available_warp_modes.update(
                {
                    str(m.get("id")): bool(m.get("installed"))
                    for m in modes
                    if isinstance(m, dict) and m.get("id")
                }
            )
        ok = resp.status == 200 and isinstance(modes, list) and "wireproxy" in installed
        detail = f"status={resp.status}, installed={','.join(str(x) for x in installed)}"
        return (
            pass_result("admin", "warp-modes", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "warp-modes", detail, required=True, elapsed=resp.elapsed)
        )

    def _warp_config() -> ProbeResult:
        resp = client.get("/api/v1/admin/warp/config", auth=True)
        ok = resp.status == 200 and "warp_mode" in resp.data
        detail = (
            f"status={resp.status}, warp_mode={resp.data.get('warp_mode')!r}, "
            f"socks_port={resp.data.get('warp_socks_port')!r}"
        )
        return (
            pass_result("admin", "warp-config", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "warp-config", detail, required=True, elapsed=resp.elapsed)
        )

    def _sources_config() -> ProbeResult:
        resp = client.get("/api/v1/admin/sources/config", auth=True)
        total = len(resp.data) if isinstance(resp.data, dict) else 0
        ok = resp.status == 200 and total > 0
        detail = f"status={resp.status}, entries={total}"
        return (
            pass_result("admin", "sources-config", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "sources-config", detail, required=True, elapsed=resp.elapsed)
        )

    def _proxy_config() -> ProbeResult:
        resp = client.get("/api/v1/admin/proxy", auth=True)
        ok = resp.status == 200 and "socks_supported" in resp.data
        detail = (
            f"status={resp.status}, proxy_set={bool(resp.data.get('proxy'))}, "
            f"pool={len(resp.data.get('proxy_pool') or [])}, "
            f"socks_supported={resp.data.get('socks_supported')!r}"
        )
        return (
            pass_result("admin", "proxy", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "proxy", detail, required=True, elapsed=resp.elapsed)
        )

    def _doctor() -> ProbeResult:
        resp = client.get("/api/v1/admin/doctor", auth=True, timeout=60)
        ok = resp.status == 200 and int(resp.data.get("total") or 0) > 0
        detail = (
            f"status={resp.status}, total={resp.data.get('total')!r}, ok={resp.data.get('ok')!r}"
        )
        return (
            pass_result("admin", "doctor", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "doctor", detail, required=True, elapsed=resp.elapsed)
        )

    def _plugins() -> ProbeResult:
        resp = client.get("/api/v1/admin/plugins", auth=True)
        plugins = resp.data.get("plugins")
        total = len(plugins) if isinstance(plugins, list) else 0
        ok = resp.status == 200 and isinstance(plugins, list)
        detail = f"status={resp.status}, plugins={total}"
        return (
            pass_result("admin", "plugins", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "plugins", detail, required=True, elapsed=resp.elapsed)
        )

    def _config_yaml() -> ProbeResult:
        resp = client.get("/api/v1/admin/config/yaml", auth=True)
        ok = resp.status == 200 and isinstance(resp.data.get("content"), str)
        detail = (
            f"status={resp.status}, path={resp.data.get('path')!r}, "
            f"content_len={len(resp.data.get('content') or '')}"
        )
        return (
            pass_result("admin", "config-yaml", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result("admin", "config-yaml", detail, required=True, elapsed=resp.elapsed)
        )

    def _source_config_openalex() -> ProbeResult:
        resp = client.get("/api/v1/admin/sources/config/openalex", auth=True)
        ok = resp.status == 200 and resp.data.get("name") == "openalex"
        detail = (
            f"status={resp.status}, enabled={resp.data.get('enabled')!r}, "
            f"integration={resp.data.get('integration_type')!r}"
        )
        return (
            pass_result(
                "admin",
                "source-config-openalex",
                detail,
                required=True,
                elapsed=resp.elapsed,
            )
            if ok
            else fail_result(
                "admin",
                "source-config-openalex",
                detail,
                required=True,
                elapsed=resp.elapsed,
            )
        )

    def _warp_components() -> ProbeResult:
        resp = client.get("/api/v1/admin/warp/components", auth=True)
        components = resp.data.get("components")
        total = len(components) if isinstance(components, list) else 0
        ok = resp.status == 200 and isinstance(components, list)
        detail = f"status={resp.status}, components={total}"
        return (
            pass_result("admin", "warp-components", detail, required=True, elapsed=resp.elapsed)
            if ok
            else fail_result(
                "admin", "warp-components", detail, required=True, elapsed=resp.elapsed
            )
        )

    for name, func in [
        ("ping", _admin_ping),
        ("config", _config),
        ("config-yaml", _config_yaml),
        ("http-backend-get", _http_backend_get),
        ("proxy", _proxy_config),
        ("warp-status", _warp_status),
        ("warp-modes", _warp_modes),
        ("warp-config", _warp_config),
        ("warp-components", _warp_components),
        ("sources-config", _sources_config),
        ("source-config-openalex", _source_config_openalex),
        ("doctor", _doctor),
        ("plugins", _plugins),
    ]:
        results.append(safe_call("admin", name, func, required=True))
    return results


def set_http_backend(
    client: ApiClient,
    backend: str,
    *,
    section: str = "matrix",
    name: str | None = None,
    required: bool = True,
) -> ProbeResult:
    resp = client.put(
        "/api/v1/admin/http-backend",
        params={"default": backend},
        auth=True,
    )
    ok = resp.status == 200 and resp.data.get("default") == backend
    detail = f"status={resp.status}, default={resp.data.get('default')!r}"
    check_name = name or f"http-backend={backend}"
    return (
        pass_result(section, check_name, detail, required=required, elapsed=resp.elapsed)
        if ok
        else fail_result(section, check_name, detail, required=required, elapsed=resp.elapsed)
    )


def set_warp(
    client: ApiClient,
    enabled: bool,
    config: SmokeConfig,
    *,
    mode: str = "auto",
    section: str = "matrix",
    name: str | None = None,
    required: bool | None = None,
) -> ProbeResult:
    check_name = name or (f"warp-enable={mode}" if enabled else "warp-disable")
    is_required = (
        config.require_warp
        if required is None and enabled
        else True
        if required is None
        else required
    )
    if enabled:
        resp = client.post(
            "/api/v1/admin/warp/enable",
            params={"mode": mode, "socks_port": 1080, "http_port": 0},
            auth=True,
            timeout=max(config.request_timeout, 90.0),
        )
        ok = resp.status == 200 and resp.data.get("ok") is True
        detail = (
            f"status={resp.status}, ok={resp.data.get('ok')!r}, "
            f"mode={resp.data.get('mode')!r}, ip={resp.data.get('ip')!r}"
        )
        return (
            pass_result(
                section,
                check_name,
                detail,
                required=is_required,
                elapsed=resp.elapsed,
                meta={
                    "requested_mode": mode,
                    "mode": resp.data.get("mode"),
                    "ip": resp.data.get("ip"),
                },
            )
            if ok
            else fail_result(
                section,
                check_name,
                detail or str(resp.data),
                required=is_required,
                elapsed=resp.elapsed,
                meta={
                    "requested_mode": mode,
                    "mode": resp.data.get("mode"),
                    "ip": resp.data.get("ip"),
                },
            )
        )

    resp = client.post(
        "/api/v1/admin/warp/disable", auth=True, timeout=max(config.request_timeout, 60.0)
    )
    ok = resp.status == 200 and resp.data.get("ok") is True
    already_disabled = resp.status == 400 and "未启用" in str(resp.data)
    detail = f"status={resp.status}, ok={resp.data.get('ok')!r}, detail={resp.data.get('detail')!r}"
    if ok or already_disabled:
        return pass_result(
            section,
            check_name,
            detail,
            required=is_required,
            elapsed=resp.elapsed,
            meta={"requested_mode": "off", "mode": "off"},
        )
    return fail_result(
        section,
        check_name,
        detail,
        required=is_required,
        elapsed=resp.elapsed,
        meta={"requested_mode": "off", "mode": "off"},
    )


def verify_warp(client: ApiClient, config: SmokeConfig) -> ProbeResult:
    resp = client.post(
        "/api/v1/admin/warp/test", auth=True, timeout=max(config.request_timeout, 45.0)
    )
    ok = resp.status == 200 and resp.data.get("ok") is True
    detail = (
        f"status={resp.status}, ok={resp.data.get('ok')!r}, "
        f"mode={resp.data.get('mode')!r}, ip={resp.data.get('ip')!r}"
    )
    return (
        pass_result(
            "matrix",
            "warp-test",
            detail,
            required=config.require_warp,
            elapsed=resp.elapsed,
            meta={
                "mode": resp.data.get("mode"),
                "ip": resp.data.get("ip"),
                "protocol": resp.data.get("protocol"),
                "proxy_type": resp.data.get("proxy_type"),
            },
        )
        if ok
        else fail_result(
            "matrix",
            "warp-test",
            detail,
            required=config.require_warp,
            elapsed=resp.elapsed,
            meta={
                "mode": resp.data.get("mode"),
                "ip": resp.data.get("ip"),
                "protocol": resp.data.get("protocol"),
                "proxy_type": resp.data.get("proxy_type"),
            },
        )
    )


def summarize_search_response(data: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    total = int(data.get("total") or 0)
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    succeeded = meta.get("succeeded") if isinstance(meta.get("succeeded"), list) else []
    failed = meta.get("failed") if isinstance(meta.get("failed"), list) else []
    return total, [str(x) for x in succeeded], [str(x) for x in failed]


def grouped_result_counts(data: dict[str, Any]) -> dict[str, int]:
    """Return result counts keyed by SearchResponse.source."""
    counts: dict[str, int] = {}
    groups = data.get("results")
    if not isinstance(groups, list):
        return counts
    for group in groups:
        if not isinstance(group, dict):
            continue
        source = str(group.get("source") or "")
        if not source:
            continue
        items = group.get("results")
        counts[source] = len(items) if isinstance(items, list) else 0
    return counts


def web_result_counts(data: dict[str, Any]) -> dict[str, int]:
    """Return result counts keyed by WebSearchResult.engine."""
    counts: dict[str, int] = {}
    items = data.get("results")
    if not isinstance(items, list):
        return counts
    for item in items:
        if not isinstance(item, dict):
            continue
        engine = str(item.get("engine") or "")
        if not engine:
            continue
        counts[engine] = counts.get(engine, 0) + 1
    return counts


def usable_sources(requested: list[str], counts: dict[str, int]) -> list[str]:
    return [source for source in requested if counts.get(source, 0) > 0]


def format_source_counts(requested: list[str], counts: dict[str, int]) -> str:
    return ",".join(f"{source}:{counts.get(source, 0)}" for source in requested) or "-"


def search_paper(
    client: ApiClient,
    name: str,
    sources: list[str],
    *,
    min_succeeded: int,
    required: bool,
) -> ProbeResult:
    resp = client.get(
        "/api/v1/search/paper",
        params={
            "q": "machine learning",
            "sources": ",".join(sources),
            "per_page": 3,
            "timeout": 90,
        },
        auth=True,
        timeout=120,
    )
    total, succeeded, failed = summarize_search_response(resp.data)
    counts = grouped_result_counts(resp.data)
    usable = usable_sources(sources, counts)
    ok = resp.status == 200 and len(usable) >= min_succeeded and total > 0
    detail = (
        f"status={resp.status}, total={total}, usable={len(usable)}/{len(sources)} "
        f"({','.join(usable) or '-'}), succeeded={','.join(succeeded) or '-'}, "
        f"failed={','.join(failed) or '-'}"
    )
    meta = {
        "matrix_kind": "paper",
        "requested": sources,
        "succeeded": succeeded,
        "failed": failed,
        "usable": usable,
        "counts": counts,
        "total": total,
    }
    return (
        pass_result(
            "zero-key-paper", name, detail, required=required, elapsed=resp.elapsed, meta=meta
        )
        if ok
        else fail_result(
            "zero-key-paper",
            name,
            detail,
            required=required,
            elapsed=resp.elapsed,
            meta=meta,
        )
    )


def search_paper_source(client: ApiClient, source: str, warp: str, group: str) -> ProbeResult:
    resp = client.get(
        "/api/v1/search/paper",
        params={
            "q": "machine learning",
            "sources": source,
            "per_page": 3,
            "timeout": 45,
        },
        auth=True,
        timeout=75,
    )
    total, succeeded, failed = summarize_search_response(resp.data)
    counts = grouped_result_counts(resp.data)
    count = counts.get(source, 0)
    outcome = "pass" if resp.status == 200 and count > 0 else "warn"
    detail = (
        f"status={resp.status}, total={total}, count={count}, "
        f"succeeded={','.join(succeeded) or '-'}, failed={','.join(failed) or '-'}"
    )
    return ProbeResult(
        "zero-key-paper-source",
        f"{group}/{source}+warp-{warp}",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "paper-source",
            "group": group,
            "source": source,
            "warp": warp,
            "count": count,
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
        },
    )


def search_patent(client: ApiClient, warp: str, backend: str) -> ProbeResult:
    resp = client.get(
        "/api/v1/search/patent",
        params={
            "q": "artificial intelligence",
            "sources": ",".join(ZERO_KEY_PATENT_SOURCES),
            "per_page": 3,
            "timeout": 60,
        },
        auth=True,
        timeout=90,
    )
    total, succeeded, failed = summarize_search_response(resp.data)
    counts = grouped_result_counts(resp.data)
    usable = usable_sources(ZERO_KEY_PATENT_SOURCES, counts)
    outcome = "pass" if resp.status == 200 and usable else "warn"
    detail = (
        f"status={resp.status}, total={total}, usable={len(usable)}/"
        f"{len(ZERO_KEY_PATENT_SOURCES)} ({','.join(usable) or '-'}), "
        f"counts={format_source_counts(ZERO_KEY_PATENT_SOURCES, counts)}, "
        f"failed={','.join(failed) or '-'}"
    )
    return ProbeResult(
        "zero-key-patent",
        f"{backend}+warp-{warp}",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "patent",
            "backend": backend,
            "warp": warp,
            "requested": ZERO_KEY_PATENT_SOURCES,
            "succeeded": succeeded,
            "failed": failed,
            "usable": usable,
            "counts": counts,
            "total": total,
        },
    )


def search_patent_source(client: ApiClient, source: str, warp: str, backend: str) -> ProbeResult:
    resp = client.get(
        "/api/v1/search/patent",
        params={
            "q": "artificial intelligence",
            "sources": source,
            "per_page": 3,
            "timeout": 45,
        },
        auth=True,
        timeout=75,
    )
    total, succeeded, failed = summarize_search_response(resp.data)
    counts = grouped_result_counts(resp.data)
    count = counts.get(source, 0)
    outcome = "pass" if resp.status == 200 and count > 0 else "warn"
    detail = (
        f"status={resp.status}, total={total}, count={count}, "
        f"succeeded={','.join(succeeded) or '-'}, failed={','.join(failed) or '-'}"
    )
    return ProbeResult(
        "zero-key-patent-source",
        f"{source}+{backend}+warp-{warp}",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "patent-source",
            "source": source,
            "backend": backend,
            "warp": warp,
            "count": count,
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
        },
    )


def search_web(client: ApiClient, warp: str, backend: str, *, required_min: int = 0) -> ProbeResult:
    resp = client.get(
        "/api/v1/search/web",
        params={
            "q": "machine learning",
            "engines": ",".join(ZERO_KEY_WEB_SCRAPERS),
            "max_results": 3,
            "timeout": 90,
        },
        auth=True,
        timeout=120,
    )
    total, succeeded, failed = summarize_search_response(resp.data)
    counts = web_result_counts(resp.data)
    usable = usable_sources(ZERO_KEY_WEB_SCRAPERS, counts)
    reached_min = len(usable) >= required_min and total > 0
    if required_min > 0:
        outcome = "pass" if resp.status == 200 and reached_min else "fail"
        required = True
    else:
        outcome = "pass" if resp.status == 200 and total > 0 else "warn"
        required = False
    detail = (
        f"status={resp.status}, total={total}, usable={len(usable)}/"
        f"{len(ZERO_KEY_WEB_SCRAPERS)} ({','.join(usable) or '-'}), "
        f"counts={format_source_counts(ZERO_KEY_WEB_SCRAPERS, counts)}, "
        f"failed={','.join(failed) or '-'}"
    )
    return ProbeResult(
        "zero-key-web",
        f"{backend}+warp-{warp}",
        outcome,
        detail,
        required,
        resp.elapsed,
        {
            "matrix_kind": "web",
            "backend": backend,
            "warp": warp,
            "requested": ZERO_KEY_WEB_SCRAPERS,
            "succeeded": succeeded,
            "failed": failed,
            "usable": usable,
            "counts": counts,
            "total": total,
        },
    )


def search_web_engine(client: ApiClient, engine: str, warp: str, backend: str) -> ProbeResult:
    resp = client.get(
        "/api/v1/search/web",
        params={
            "q": "machine learning",
            "engines": engine,
            "max_results": 3,
            "timeout": 45,
        },
        auth=True,
        timeout=75,
    )
    total, succeeded, failed = summarize_search_response(resp.data)
    counts = web_result_counts(resp.data)
    count = counts.get(engine, 0)
    outcome = "pass" if resp.status == 200 and count > 0 else "warn"
    detail = (
        f"status={resp.status}, total={total}, count={count}, "
        f"succeeded={','.join(succeeded) or '-'}, failed={','.join(failed) or '-'}"
    )
    return ProbeResult(
        "zero-key-web-source",
        f"{engine}+{backend}+warp-{warp}",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "web-source",
            "source": engine,
            "backend": backend,
            "warp": warp,
            "count": count,
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
        },
    )


def search_open_source_group(client: ApiClient) -> ProbeResult:
    resp = client.get(
        "/api/v1/search/web",
        params={
            "q": "machine learning",
            "engines": ",".join(ZERO_KEY_OPEN_SEARCH_SOURCES),
            "max_results": 2,
            "timeout": 120,
        },
        auth=True,
        timeout=150,
    )
    total, succeeded, failed = summarize_search_response(resp.data)
    counts = web_result_counts(resp.data)
    usable = usable_sources(ZERO_KEY_OPEN_SEARCH_SOURCES, counts)
    outcome = "pass" if resp.status == 200 and total > 0 else "warn"
    detail = (
        f"status={resp.status}, total={total}, usable={len(usable)}/"
        f"{len(ZERO_KEY_OPEN_SEARCH_SOURCES)} ({','.join(usable) or '-'}), "
        f"counts={format_source_counts(ZERO_KEY_OPEN_SEARCH_SOURCES, counts)}, "
        f"failed={','.join(failed) or '-'}"
    )
    return ProbeResult(
        "zero-key-open-search",
        "optional-key-and-open-sources",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "open-search",
            "requested": ZERO_KEY_OPEN_SEARCH_SOURCES,
            "succeeded": succeeded,
            "failed": failed,
            "usable": usable,
            "counts": counts,
            "total": total,
        },
    )


def search_media(client: ApiClient, kind: str) -> ProbeResult:
    path = "/api/v1/search/images" if kind == "images" else "/api/v1/search/videos"
    resp = client.get(
        path,
        params={"q": "machine learning", "max_results": 5, "timeout": 45},
        auth=True,
        timeout=75,
    )
    total, succeeded, failed = summarize_search_response(resp.data)
    outcome = "pass" if resp.status == 200 and total > 0 else "warn"
    detail = (
        f"status={resp.status}, total={total}, succeeded={','.join(succeeded) or '-'}, "
        f"failed={','.join(failed) or '-'}"
    )
    return ProbeResult(
        "zero-key-media",
        f"duckduckgo-{kind}",
        outcome,
        detail,
        False,
        resp.elapsed,
        {"succeeded": succeeded, "failed": failed, "total": total},
    )


def list_sources_inventory(client: ApiClient) -> ProbeResult:
    resp = client.get("/api/v1/sources", auth=True)
    categories = len(resp.data) if isinstance(resp.data, dict) else 0
    total = 0
    if isinstance(resp.data, dict):
        total = sum(len(items) for items in resp.data.values() if isinstance(items, list))
    ok = resp.status == 200 and total > 0
    detail = f"status={resp.status}, categories={categories}, entries={total}"
    return (
        pass_result(
            "zero-key-route",
            "sources",
            detail,
            required=True,
            elapsed=resp.elapsed,
            meta={"matrix_kind": "direct-route", "route": "/api/v1/sources", "count": total},
        )
        if ok
        else fail_result(
            "zero-key-route",
            "sources",
            detail,
            required=True,
            elapsed=resp.elapsed,
            meta={"matrix_kind": "direct-route", "route": "/api/v1/sources", "count": total},
        )
    )


def _result_list_count(data: Any, key: str = "results") -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return len(data[key])
    return 0


def _first_bilibili_bvid(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list):
        return None
    for item in results:
        if not isinstance(item, dict):
            continue
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
        bvid = raw.get("bvid")
        if bvid:
            return str(bvid)
        url = str(item.get("url") or "")
        marker = "/video/"
        if marker in url:
            return url.split(marker, 1)[1].split("?", 1)[0].strip("/")
    return None


def bilibili_search_route(client: ApiClient) -> ProbeResult:
    resp = client.get(
        "/api/v1/bilibili/search",
        params={"keyword": "机器学习", "max_results": 3},
        auth=True,
        timeout=75,
    )
    count = _result_list_count(resp.data)
    outcome = "pass" if resp.status == 200 and count > 0 else "warn"
    detail = f"status={resp.status}, results={count}"
    return ProbeResult(
        "zero-key-route",
        "bilibili-search",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "direct-route",
            "route": "/api/v1/bilibili/search",
            "count": count,
        },
    )


def bilibili_users_route(client: ApiClient) -> ProbeResult:
    resp = client.get(
        "/api/v1/bilibili/search/users",
        params={"keyword": "清华大学", "max_results": 3},
        auth=True,
        timeout=75,
    )
    count = _result_list_count(resp.data)
    outcome = "pass" if resp.status == 200 and count > 0 else "warn"
    detail = f"status={resp.status}, users={count}"
    return ProbeResult(
        "zero-key-route",
        "bilibili-users",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "direct-route",
            "route": "/api/v1/bilibili/search/users",
            "count": count,
        },
    )


def bilibili_articles_route(client: ApiClient) -> ProbeResult:
    resp = client.get(
        "/api/v1/bilibili/search/articles",
        params={"keyword": "人工智能", "max_results": 3},
        auth=True,
        timeout=75,
    )
    count = _result_list_count(resp.data)
    outcome = "pass" if resp.status == 200 and count > 0 else "warn"
    detail = f"status={resp.status}, articles={count}"
    return ProbeResult(
        "zero-key-route",
        "bilibili-articles",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "direct-route",
            "route": "/api/v1/bilibili/search/articles",
            "count": count,
        },
    )


def bilibili_video_detail_route(client: ApiClient) -> ProbeResult:
    search_resp = client.get(
        "/api/v1/bilibili/search",
        params={"keyword": "机器学习", "max_results": 1},
        auth=True,
        timeout=75,
    )
    bvid = _first_bilibili_bvid(search_resp.data) or "BV1Q5411W7tN"
    resp = client.get(f"/api/v1/bilibili/video/{bvid}", auth=True, timeout=75)
    title = resp.data.get("title") if isinstance(resp.data, dict) else None
    ok = resp.status == 200 and bool(title)
    outcome = "pass" if ok else "warn"
    detail = f"status={resp.status}, bvid={bvid}, title={bool(title)}"
    return ProbeResult(
        "zero-key-route",
        "bilibili-video-detail",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "direct-route",
            "route": "/api/v1/bilibili/video/{bvid}",
            "count": 1 if ok else 0,
        },
    )


def fetch_builtin(client: ApiClient) -> ProbeResult:
    resp = client.post(
        "/api/v1/fetch",
        body={
            "urls": ["https://example.com/"],
            "provider": "builtin",
            "timeout": 15,
            "max_length": 1200,
            "respect_robots_txt": False,
        },
        auth=True,
        timeout=45,
    )
    ok_count = int(resp.data.get("total_ok") or 0)
    failed_count = int(resp.data.get("total_failed") or 0)
    ok = resp.status == 200 and ok_count >= 1
    detail = f"status={resp.status}, total_ok={ok_count}, total_failed={failed_count}"
    return (
        pass_result("zero-key-fetch", "builtin-fetch", detail, required=True, elapsed=resp.elapsed)
        if ok
        else fail_result(
            "zero-key-fetch", "builtin-fetch", detail, required=True, elapsed=resp.elapsed
        )
    )


def fetch_jina_reader(client: ApiClient) -> ProbeResult:
    resp = client.post(
        "/api/v1/fetch",
        body={
            "urls": ["https://example.com/"],
            "provider": "jina_reader",
            "timeout": 20,
            "max_length": 1200,
            "respect_robots_txt": False,
        },
        auth=True,
        timeout=45,
    )
    ok_count = int(resp.data.get("total_ok") or 0)
    failed_count = int(resp.data.get("total_failed") or 0)
    outcome = "pass" if resp.status == 200 and ok_count >= 1 else "warn"
    detail = f"status={resp.status}, total_ok={ok_count}, total_failed={failed_count}"
    return ProbeResult(
        "zero-key-fetch",
        "jina-reader-fetch",
        outcome,
        detail,
        False,
        resp.elapsed,
        {"total_ok": ok_count, "total_failed": failed_count},
    )


def fetch_provider_probe(
    client: ApiClient,
    provider_test: dict[str, Any],
    *,
    warp: str,
    backend: str,
) -> ProbeResult:
    provider = str(provider_test["provider"])
    urls = list(provider_test["urls"])
    timeout = float(provider_test.get("timeout", 20))
    resp = client.post(
        "/api/v1/fetch",
        body={
            "urls": urls,
            "provider": provider,
            "timeout": timeout,
            "max_length": 1200,
            "respect_robots_txt": False,
        },
        auth=True,
        timeout=max(timeout + 20, 45),
    )
    ok_count = int(resp.data.get("total_ok") or 0)
    failed_count = int(resp.data.get("total_failed") or 0)
    total = int(resp.data.get("total") or ok_count + failed_count)
    outcome = "pass" if resp.status == 200 and ok_count >= 1 else "warn"
    detail = (
        f"status={resp.status}, total_ok={ok_count}, total_failed={failed_count}, "
        f"note={provider_test.get('note', '-')}"
    )
    return ProbeResult(
        "zero-key-fetch-source",
        f"{provider}+{backend}+warp-{warp}",
        outcome,
        detail,
        False,
        resp.elapsed,
        {
            "matrix_kind": "fetch-source",
            "provider": provider,
            "backend": backend,
            "warp": warp,
            "urls": urls,
            "total": total,
            "total_ok": ok_count,
            "total_failed": failed_count,
            "note": provider_test.get("note", ""),
        },
    )


def skipped_fetch_provider(provider: str, reason: str) -> ProbeResult:
    return ProbeResult(
        "zero-key-fetch-source",
        provider,
        "skip",
        reason,
        False,
        None,
        {
            "matrix_kind": "fetch-source",
            "provider": provider,
            "backend": "-",
            "warp": "-",
            "urls": [],
            "total": 0,
            "total_ok": 0,
            "total_failed": 0,
            "note": reason,
        },
    )


def links_extract(client: ApiClient) -> ProbeResult:
    resp = client.get(
        "/api/v1/links",
        params={"url": "https://example.com/", "limit": 20},
        auth=True,
        timeout=45,
    )
    total = (
        resp.data.get("total") or len(resp.data.get("links", []))
        if isinstance(resp.data, dict)
        else 0
    )
    ok = resp.status == 200
    detail = f"status={resp.status}, total={total}"
    return (
        pass_result("zero-key-fetch", "links", detail, elapsed=resp.elapsed)
        if ok
        else warn_result("zero-key-fetch", "links", detail, elapsed=resp.elapsed)
    )


def sitemap_parse(client: ApiClient) -> ProbeResult:
    resp = client.get(
        "/api/v1/sitemap",
        params={"url": "https://example.com/sitemap.xml", "limit": 20},
        auth=True,
        timeout=45,
    )
    total = int(resp.data.get("total") or len(resp.data.get("urls", [])))
    ok = resp.status == 200
    detail = f"status={resp.status}, total={total}"
    return (
        pass_result("zero-key-fetch", "sitemap", detail, elapsed=resp.elapsed)
        if ok
        else warn_result("zero-key-fetch", "sitemap", detail, elapsed=resp.elapsed)
    )


def wayback_cdx(client: ApiClient) -> ProbeResult:
    resp = client.get(
        "/api/v1/wayback/cdx",
        params={
            "url": "example.com",
            "from": "20240101",
            "to": "20261231",
            "limit": 5,
            "timeout": 30,
        },
        auth=True,
        timeout=45,
    )
    total = int(resp.data.get("total") or len(resp.data.get("snapshots", [])))
    outcome = "pass" if resp.status == 200 and total > 0 else "warn"
    detail = f"status={resp.status}, total={total}"
    return ProbeResult(
        "zero-key-archive",
        "wayback-cdx",
        outcome,
        detail,
        False,
        resp.elapsed,
        {"total": total},
    )


def wayback_check(client: ApiClient) -> ProbeResult:
    resp = client.get(
        "/api/v1/wayback/check",
        params={"url": "https://example.com/", "timeout": 30},
        auth=True,
        timeout=45,
    )
    available = bool(resp.data.get("available"))
    outcome = "pass" if resp.status == 200 else "warn"
    detail = (
        f"status={resp.status}, available={available}, "
        f"snapshot={bool(resp.data.get('snapshot_url'))}"
    )
    return ProbeResult(
        "zero-key-archive",
        "wayback-check",
        outcome,
        detail,
        False,
        resp.elapsed,
        {"available": available},
    )


def wayback_save(client: ApiClient) -> ProbeResult:
    resp = client.post(
        "/api/v1/admin/wayback/save",
        body={"url": "https://example.com/", "timeout": 60},
        auth=True,
        timeout=90,
    )
    success = bool(resp.data.get("success"))
    outcome = "pass" if resp.status == 200 and success else "warn"
    detail = (
        f"status={resp.status}, success={success}, "
        f"snapshot={bool(resp.data.get('snapshot_url'))}, error={resp.data.get('error')!r}"
    )
    return ProbeResult(
        "zero-key-archive",
        "wayback-save",
        outcome,
        detail,
        False,
        resp.elapsed,
        {"success": success},
    )


def warp_mode_available(mode: str, state: RunState) -> bool:
    if mode == "auto":
        return True
    if not state.available_warp_modes:
        return True
    return bool(state.available_warp_modes.get(mode))


def run_zero_key_case(
    client: ApiClient,
    config: SmokeConfig,
    *,
    warp: str,
) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    results.append(
        safe_call("matrix", "http-backend=auto", lambda: set_http_backend(client, "auto"))
    )
    default_min = (
        config.min_default_paper_no_warp if warp == "off" else config.min_default_paper_warp
    )
    results.append(
        safe_call(
            "zero-key-paper",
            f"default-paper-warp-{warp}",
            lambda: search_paper(
                client,
                f"default-paper-warp-{warp}",
                DEFAULT_PAPER_SOURCES,
                min_succeeded=default_min,
                required=True,
            ),
            required=True,
        )
    )
    results.append(
        safe_call(
            "zero-key-paper",
            f"extra-paper-warp-{warp}",
            lambda: search_paper(
                client,
                f"extra-paper-warp-{warp}",
                EXTRA_ZERO_KEY_PAPER_SOURCES,
                min_succeeded=1,
                required=False,
            ),
        )
    )

    if config.full_matrix:
        for group, sources in [
            ("default", DEFAULT_PAPER_SOURCES),
            ("extra", EXTRA_ZERO_KEY_PAPER_SOURCES),
        ]:
            for source in sources:
                results.append(
                    safe_call(
                        "zero-key-paper-source",
                        f"{group}/{source}+warp-{warp}",
                        lambda source=source, group=group: search_paper_source(
                            client, source, warp, group
                        ),
                    )
                )

    for backend in MATRIX_HTTP_BACKENDS:
        results.append(
            safe_call(
                "matrix",
                f"http-backend={backend}",
                lambda backend=backend: set_http_backend(client, backend),
                required=True,
            )
        )
        if results[-1].outcome == "fail":
            continue

        results.append(
            safe_call(
                "zero-key-patent",
                f"{backend}+warp-{warp}",
                lambda backend=backend: search_patent(client, warp, backend),
            )
        )
        if config.full_matrix:
            for source in ZERO_KEY_PATENT_SOURCES:
                results.append(
                    safe_call(
                        "zero-key-patent-source",
                        f"{source}+{backend}+warp-{warp}",
                        lambda source=source, backend=backend: search_patent_source(
                            client, source, warp, backend
                        ),
                    )
                )

        required_min = (
            config.min_best_web_engines if backend == "curl_cffi" and warp != "off" else 0
        )
        results.append(
            safe_call(
                "zero-key-web",
                f"{backend}+warp-{warp}",
                lambda backend=backend, required_min=required_min: search_web(
                    client,
                    warp,
                    backend,
                    required_min=required_min,
                ),
                required=required_min > 0,
            )
        )
        if config.full_matrix:
            for engine in ZERO_KEY_WEB_SCRAPERS:
                results.append(
                    safe_call(
                        "zero-key-web-source",
                        f"{engine}+{backend}+warp-{warp}",
                        lambda engine=engine, backend=backend: search_web_engine(
                            client, engine, warp, backend
                        ),
                    )
                )
            for provider_test in ZERO_KEY_FETCH_PROVIDER_TESTS:
                if not provider_test.get("backend_matrix"):
                    continue
                provider = str(provider_test["provider"])
                results.append(
                    safe_call(
                        "zero-key-fetch-source",
                        f"{provider}+{backend}+warp-{warp}",
                        lambda provider_test=provider_test, backend=backend: fetch_provider_probe(
                            client,
                            provider_test,
                            warp=warp,
                            backend=backend,
                        ),
                    )
                )

    if config.full_matrix:
        results.append(
            safe_call("matrix", "http-backend=auto", lambda: set_http_backend(client, "auto"))
        )
        for provider_test in ZERO_KEY_FETCH_PROVIDER_TESTS:
            if provider_test.get("backend_matrix"):
                continue
            provider = str(provider_test["provider"])
            results.append(
                safe_call(
                    "zero-key-fetch-source",
                    f"{provider}+auto+warp-{warp}",
                    lambda provider_test=provider_test: fetch_provider_probe(
                        client,
                        provider_test,
                        warp=warp,
                        backend="auto",
                    ),
                )
            )

    return results


def run_zero_key_checks(
    client: ApiClient,
    config: SmokeConfig,
    state: RunState,
) -> list[ProbeResult]:
    if not state.admin_available:
        return [skip_result("matrix", "zero-key-matrix", "admin access unavailable")]
    if not (state.backend_snapshot_ok and state.warp_snapshot_ok):
        missing = []
        if not state.backend_snapshot_ok:
            missing.append("http-backend")
        if not state.warp_snapshot_ok:
            missing.append("warp")
        return [
            fail_result(
                "matrix",
                "mutation-snapshot",
                f"missing original state snapshot: {','.join(missing)}; "
                "mutation matrix skipped to avoid unsafe restore",
                required=True,
            )
        ]

    results: list[ProbeResult] = []

    disable = safe_call(
        "matrix", "warp-disable", lambda: set_warp(client, False, config), required=True
    )
    results.append(disable)
    if disable.outcome == "fail":
        return results

    results.extend(run_zero_key_case(client, config, warp="off"))

    for index, mode in enumerate(config.warp_modes):
        if not warp_mode_available(mode, state):
            results.append(
                skip_result("matrix", f"warp-enable={mode}", "WARP mode is not available")
            )
            continue

        if index > 0:
            reset = safe_call(
                "matrix",
                f"warp-reset-before={mode}",
                lambda: set_warp(client, False, config),
                required=True,
            )
            results.append(reset)
            if reset.outcome == "fail":
                continue

        enable = safe_call(
            "matrix",
            f"warp-enable={mode}",
            lambda mode=mode: set_warp(client, True, config, mode=mode),
            required=config.require_warp,
        )
        results.append(enable)
        if enable.outcome == "fail":
            continue

        verify = safe_call(
            "matrix",
            f"warp-test={mode}",
            lambda: verify_warp(client, config),
            required=config.require_warp,
        )
        results.append(verify)
        state.warp_available = state.warp_available or verify.outcome != "fail"
        if verify.outcome == "fail":
            continue

        state.observed_warp_status[mode] = dict(verify.meta)
        results.extend(run_zero_key_case(client, config, warp=mode))

    results.append(
        safe_call("matrix", "http-backend=auto", lambda: set_http_backend(client, "auto"))
    )
    current_warp_label = (
        list(state.observed_warp_status.keys())[-1] if state.observed_warp_status else "off"
    )
    results.append(
        safe_call(
            "zero-key-web",
            f"auto+warp-{current_warp_label}",
            lambda: search_web(client, current_warp_label, "auto"),
        )
    )
    results.append(
        safe_call(
            "zero-key-open-search",
            "optional-key-and-open-sources",
            lambda: search_open_source_group(client),
        )
    )
    results.append(
        safe_call("zero-key-media", "duckduckgo-images", lambda: search_media(client, "images"))
    )
    results.append(
        safe_call("zero-key-media", "duckduckgo-videos", lambda: search_media(client, "videos"))
    )
    results.append(
        safe_call(
            "zero-key-route",
            "sources",
            lambda: list_sources_inventory(client),
            required=True,
        )
    )
    results.append(
        safe_call("zero-key-route", "bilibili-search", lambda: bilibili_search_route(client))
    )
    results.append(
        safe_call("zero-key-route", "bilibili-users", lambda: bilibili_users_route(client))
    )
    results.append(
        safe_call("zero-key-route", "bilibili-articles", lambda: bilibili_articles_route(client))
    )
    results.append(
        safe_call(
            "zero-key-route",
            "bilibili-video-detail",
            lambda: bilibili_video_detail_route(client),
        )
    )
    results.append(
        safe_call("zero-key-fetch", "builtin-fetch", lambda: fetch_builtin(client), required=True)
    )
    results.append(
        safe_call("zero-key-fetch", "jina-reader-fetch", lambda: fetch_jina_reader(client))
    )
    results.append(safe_call("zero-key-fetch", "links", lambda: links_extract(client)))
    results.append(safe_call("zero-key-fetch", "sitemap", lambda: sitemap_parse(client)))
    results.append(safe_call("zero-key-archive", "wayback-cdx", lambda: wayback_cdx(client)))
    results.append(safe_call("zero-key-archive", "wayback-check", lambda: wayback_check(client)))
    results.append(safe_call("zero-key-archive", "wayback-save", lambda: wayback_save(client)))
    if config.full_matrix:
        for item in ZERO_KEY_FETCH_SKIPPED:
            results.append(skipped_fetch_provider(item["provider"], item["reason"]))

    return results


def restore_state(client: ApiClient, state: RunState) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    if not state.admin_available:
        return results

    if state.backend_snapshot_ok and state.original_backend:
        results.append(
            safe_call(
                "restore",
                "http-backend",
                lambda: set_http_backend(
                    client,
                    str(state.original_backend),
                    section="restore",
                    name="http-backend",
                    required=True,
                ),
            )
        )
    else:
        results.append(
            skip_result(
                "restore",
                "http-backend",
                "original backend snapshot unavailable; no restore attempted",
            )
        )

    if not state.warp_snapshot_ok or state.original_warp_status is None:
        results.append(
            skip_result(
                "restore",
                "warp",
                "original WARP snapshot unavailable; no restore attempted",
            )
        )
        return results

    original_status = state.original_warp_status.get("status")
    original_mode = state.original_warp_status.get("mode") or "auto"
    original_socks = state.original_warp_status.get("socks_port") or 1080
    original_http = state.original_warp_status.get("http_port") or 0
    if original_status == "enabled":

        def _restore_warp_enabled() -> ProbeResult:
            disable_resp = client.post("/api/v1/admin/warp/disable", auth=True, timeout=60)
            if disable_resp.status != 200 or disable_resp.data.get("ok") is not True:
                return warn_result(
                    "restore",
                    "warp",
                    f"disable-before-restore status={disable_resp.status}, "
                    f"detail={disable_resp.data.get('detail') or disable_resp.data.get('error')!r}",
                    elapsed=disable_resp.elapsed,
                )
            resp = client.post(
                "/api/v1/admin/warp/enable",
                params={
                    "mode": original_mode,
                    "socks_port": original_socks,
                    "http_port": original_http,
                },
                auth=True,
                timeout=90,
            )
            ok = resp.status == 200 and resp.data.get("ok") is True
            detail = (
                f"status={resp.status}, ok={resp.data.get('ok')!r}, "
                f"mode={resp.data.get('mode')!r}, ip={resp.data.get('ip')!r}"
            )
            return (
                pass_result("restore", "warp", detail, elapsed=resp.elapsed)
                if ok
                else warn_result("restore", "warp", detail, elapsed=resp.elapsed)
            )

        results.append(safe_call("restore", "warp", _restore_warp_enabled))
    else:
        results.append(
            safe_call(
                "restore",
                "warp",
                lambda: set_warp(
                    client,
                    False,
                    SmokeConfig(
                        base_url=client.config.base_url,
                        expected_version=client.config.expected_version,
                        request_timeout=client.config.request_timeout,
                        bearer_token=client.config.bearer_token,
                        require_warp=False,
                    ),
                    section="restore",
                    name="warp",
                    required=True,
                ),
            )
        )
    return results


def run_report(config: SmokeConfig) -> list[ProbeResult]:
    client = ApiClient(config)
    state = RunState()
    results: list[ProbeResult] = []
    try:
        results.extend(run_basic_checks(client, config, state))
        results.extend(run_admin_checks(client, config, state))
        if state.admin_available and not config.surface_only:
            results.extend(run_zero_key_checks(client, config, state))
    finally:
        if not config.surface_only:
            results.extend(restore_state(client, state))
    return results


def required_failures(results: list[ProbeResult]) -> list[ProbeResult]:
    return [result for result in results if result.required and result.outcome == "fail"]


def escape_summary_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def elapsed_text(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}s"


def outcome_text(result: ProbeResult) -> str:
    labels = {
        "pass": "PASS",
        "fail": "FAIL",
        "warn": "WARN",
        "skip": "SKIP",
    }
    return labels.get(result.outcome, result.outcome.upper())


def _meta_count(result: ProbeResult) -> int:
    try:
        return int(result.meta.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def append_zero_key_matrix(lines: list[str], results: list[ProbeResult]) -> None:
    aggregate = [
        result
        for result in results
        if result.meta.get("matrix_kind") in {"paper", "patent", "web", "open-search"}
    ]
    paper_sources = [
        result for result in results if result.meta.get("matrix_kind") == "paper-source"
    ]
    patent_sources = [
        result for result in results if result.meta.get("matrix_kind") == "patent-source"
    ]
    web_sources = [result for result in results if result.meta.get("matrix_kind") == "web-source"]
    fetch_sources = [
        result for result in results if result.meta.get("matrix_kind") == "fetch-source"
    ]
    open_search = [result for result in results if result.meta.get("matrix_kind") == "open-search"]
    direct_routes = [
        result for result in results if result.meta.get("matrix_kind") == "direct-route"
    ]

    if not any(
        [aggregate, paper_sources, patent_sources, web_sources, fetch_sources, direct_routes]
    ):
        return

    lines.extend(["", "## Zero-Key Matrix", ""])

    if aggregate:
        lines.extend(
            [
                "### Aggregate Probes",
                "",
                "| Probe | Backend | WARP | Result | Usable | Counts |",
                "|---|---|---|---:|---:|---|",
            ]
        )
        for result in aggregate:
            requested = result.meta.get("requested")
            counts = result.meta.get("counts")
            usable = result.meta.get("usable")
            count_text = (
                format_source_counts(list(requested), dict(counts))
                if isinstance(requested, list) and isinstance(counts, dict)
                else "-"
            )
            lines.append(
                f"| `{result.name}` | `{result.meta.get('backend', '-')}` | "
                f"`{result.meta.get('warp', '-')}` | {outcome_text(result)} | "
                f"{len(usable) if isinstance(usable, list) else '-'} | "
                f"{escape_summary_cell(count_text)} |"
            )

    if paper_sources:
        lines.extend(
            [
                "",
                "### Paper Sources",
                "",
                "| Group | Source | WARP | Result | Count | Detail |",
                "|---|---|---|---:|---:|---|",
            ]
        )
        for result in paper_sources:
            lines.append(
                f"| `{result.meta.get('group', '-')}` | `{result.meta.get('source', '-')}` | "
                f"`{result.meta.get('warp', '-')}` | {outcome_text(result)} | "
                f"{_meta_count(result)} | {escape_summary_cell(result.detail)} |"
            )

    if patent_sources:
        lines.extend(
            [
                "",
                "### Patent Sources",
                "",
                "| Source | Backend | WARP | Result | Count | Detail |",
                "|---|---|---|---|---:|---|",
            ]
        )
        for result in patent_sources:
            lines.append(
                f"| `{result.meta.get('source', '-')}` | `{result.meta.get('backend', '-')}` | "
                f"`{result.meta.get('warp', '-')}` | {outcome_text(result)} | "
                f"{_meta_count(result)} | {escape_summary_cell(result.detail)} |"
            )

    if web_sources:
        lines.extend(
            [
                "",
                "### Web Scraper Sources",
                "",
                "| Source | Backend | WARP | Result | Count | Detail |",
                "|---|---|---|---|---:|---|",
            ]
        )
        for result in web_sources:
            lines.append(
                f"| `{result.meta.get('source', '-')}` | `{result.meta.get('backend', '-')}` | "
                f"`{result.meta.get('warp', '-')}` | {outcome_text(result)} | "
                f"{_meta_count(result)} | {escape_summary_cell(result.detail)} |"
            )

    if open_search:
        lines.extend(
            [
                "",
                "### Open / Optional-Key Platform Sources",
                "",
                "| Source | Result | Count | Detail |",
                "|---|---|---:|---|",
            ]
        )
        for result in open_search:
            requested = result.meta.get("requested")
            counts = result.meta.get("counts")
            if not isinstance(requested, list) or not isinstance(counts, dict):
                continue
            for source in requested:
                count = int(counts.get(source) or 0)
                source_outcome = "PASS" if count > 0 else "WARN"
                lines.append(
                    f"| `{source}` | {source_outcome} | {count} | "
                    f"{escape_summary_cell(result.detail)} |"
                )

    if fetch_sources:
        lines.extend(
            [
                "",
                "### Fetch Providers",
                "",
                "| Provider | Backend | WARP | Result | OK/Total | Detail |",
                "|---|---|---|---|---:|---|",
            ]
        )
        for result in fetch_sources:
            total_ok = int(result.meta.get("total_ok") or 0)
            total = int(result.meta.get("total") or 0)
            lines.append(
                f"| `{result.meta.get('provider', result.name)}` | "
                f"`{result.meta.get('backend', '-')}` | `{result.meta.get('warp', '-')}` | "
                f"{outcome_text(result)} | {total_ok}/{total} | "
                f"{escape_summary_cell(result.detail)} |"
            )

    if direct_routes:
        lines.extend(
            [
                "",
                "### Direct API Routes",
                "",
                "| Route | Result | Count | Detail |",
                "|---|---|---:|---|",
            ]
        )
        for result in direct_routes:
            lines.append(
                f"| `{result.meta.get('route', result.name)}` | {outcome_text(result)} | "
                f"{int(result.meta.get('count') or 0)} | "
                f"{escape_summary_cell(result.detail)} |"
            )

    lines.extend(
        [
            "",
            "### Excluded By Design",
            "",
            "| Group | Sources | Reason |",
            "|---|---|---|",
            f"| Required-key search | `{', '.join(EXCLUDED_REQUIRED_KEY_SEARCH_SOURCES)}` | "
            "Requires API key or account credentials. |",
            f"| Self-hosted search | `{', '.join(EXCLUDED_SELF_HOSTED_SEARCH_SOURCES)}` | "
            "Requires user-managed service URL. |",
            f"| No public CD endpoint | `{', '.join(EXCLUDED_NO_PUBLIC_ENDPOINT_SOURCES)}` | "
            "Registered capability exists, but the current HFS API has no matching route. |",
            f"| Required-key fetch | `{', '.join(EXCLUDED_REQUIRED_KEY_FETCH_PROVIDERS)}` | "
            "Requires API key or paid/browser-rendering account. |",
            f"| External-runtime fetch | `{', '.join(item['provider'] for item in ZERO_KEY_FETCH_SKIPPED)}` | "
            "Requires external runtime/config rather than a public zero-key channel. |",
            f"| Required-key direct APIs | `{', '.join(EXCLUDED_REQUIRED_KEY_ROUTE_APIS)}` | "
            "Requires API credentials before the route can exercise the upstream. |",
            f"| LLM routes | `{', '.join(EXCLUDED_LLM_ROUTE_APIS)}` | "
            "Requires configured LLM service, not a zero-key public channel. |",
        ]
    )


def build_markdown_report(config: SmokeConfig, results: list[ProbeResult]) -> str:
    failures = required_failures(results)
    status = "failed" if failures else "passed"
    if config.surface_only:
        capability_lines = [
            "- WARP enable modes: `skipped (surface-only)`",
            "- HTTP backend mutation matrix: `skipped (surface-only)`",
            "- Per-source matrix: `skipped (surface-only)`",
            "- Fetch provider matrix: `skipped (surface-only)`",
            "- Direct zero-key routes: `skipped (surface-only)`",
        ]
    else:
        capability_lines = [
            f"- WARP modes: `off,{','.join(config.warp_modes)}`",
            f"- HTTP backend matrix: `{','.join(MATRIX_HTTP_BACKENDS)}`",
            f"- Per-source matrix: `{'enabled' if config.full_matrix else 'quick aggregate only'}`",
            f"- Fetch provider matrix: `{len(ZERO_KEY_FETCH_PROVIDER_TESTS)} tested, "
            f"{len(ZERO_KEY_FETCH_SKIPPED)} skipped external-runtime`",
            "- Direct zero-key routes: `/api/v1/sources`, `/api/v1/bilibili/*`, "
            "`/api/v1/wayback/*`, `/api/v1/links`, `/api/v1/sitemap`",
        ]
    lines = [
        "# SouWen HF Space CD Test Report",
        "",
        f"- Result: **{status}**",
        f"- Base URL: `{config.base_url}`",
        f"- Expected version: `{config.expected_version or 'not pinned'}`",
        f"- Mode: `{'surface-only' if config.surface_only else 'post-deploy capability'}`",
        *capability_lines,
        f"- Required failures: `{len(failures)}`",
        "",
        "## Gate Summary",
        "",
        "| Required Check | Result | Detail |",
        "|---|---:|---|",
    ]
    required = [result for result in results if result.required]
    for result in required:
        lines.append(
            f"| `{result.section}/{result.name}` | {outcome_text(result)} | "
            f"{escape_summary_cell(result.detail)} |"
        )
    if not required:
        lines.append("| `_none` | SKIP | No required checks were registered. |")

    append_zero_key_matrix(lines, results)

    sections = []
    for result in results:
        if result.section not in sections:
            sections.append(result.section)

    for section in sections:
        lines.extend(
            [
                "",
                f"## {section}",
                "",
                "| Check | Result | Required | Time | Detail |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for result in [item for item in results if item.section == section]:
            lines.append(
                f"| `{result.name}` | {outcome_text(result)} | "
                f"{'yes' if result.required else 'no'} | {elapsed_text(result.elapsed)} | "
                f"{escape_summary_cell(result.detail)} |"
            )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `FAIL` on a required row fails the workflow.",
            "- `WARN` rows are observed 0key channels that may fluctuate because of upstream anti-bot behavior, rate limits, or exit IP reputation.",
            "- Fetch provider matrix runs backend-sensitive providers across `curl_cffi/httpx`; backend-independent providers are exercised with `auto` for each WARP mode.",
            "- Required-key and self-hosted channels are intentionally excluded.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_text(path: str | None, content: str, *, append: bool = False) -> None:
    if not path:
        return
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as file:
        file.write(content)
        if not content.endswith("\n"):
            file.write("\n")


def write_json(path: str | None, results: list[ProbeResult]) -> None:
    if not path:
        return
    payload = [
        {
            "section": item.section,
            "name": item.name,
            "outcome": item.outcome,
            "required": item.required,
            "detail": item.detail,
            "elapsed": item.elapsed,
            "meta": item.meta,
        }
        for item in results
    ]
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def print_console_report(results: list[ProbeResult]) -> None:
    for result in results:
        req = " required" if result.required else ""
        print(
            f"{outcome_text(result)} {result.section}/{result.name}{req}: "
            f"{result.detail} ({elapsed_text(result.elapsed)})",
            flush=True,
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SOUWEN_HF_SPACE_URL", DEFAULT_BASE_URL),
        help=f"Public Space URL. Defaults to {DEFAULT_BASE_URL}.",
    )
    parser.add_argument(
        "--expected-version",
        default=os.environ.get("EXPECTED_SOUWEN_VERSION"),
        help="Expected SouWen version reported by /health, /readiness and /openapi.json.",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=float(os.environ.get("SOUWEN_SMOKE_REQUEST_TIMEOUT", "25")),
        help="Default per-request timeout.",
    )
    parser.add_argument(
        "--summary-file",
        default=os.environ.get("GITHUB_STEP_SUMMARY"),
        help="Markdown file to append the report to.",
    )
    parser.add_argument(
        "--report-file",
        default=os.environ.get("SOUWEN_SMOKE_REPORT_FILE", "hf-space-cd-report.md"),
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--json-file",
        default=os.environ.get("SOUWEN_SMOKE_JSON_FILE", "hf-space-cd-report.json"),
        help="JSON result output path.",
    )
    parser.add_argument(
        "--bearer-token",
        default=os.environ.get("SOUWEN_SMOKE_BEARER_TOKEN"),
        help="Optional admin Bearer token. If omitted, the script relies on SOUWEN_ADMIN_OPEN=1.",
    )
    parser.add_argument(
        "--warp-modes",
        default=os.environ.get("SOUWEN_SMOKE_WARP_MODES", ",".join(DEFAULT_WARP_MODES)),
        help=(
            "Comma-separated WARP enable modes to test after the warp-off matrix. "
            "Use values such as auto,wireproxy,usque."
        ),
    )
    parser.add_argument(
        "--quick-matrix",
        action="store_true",
        help="Only run aggregate 0key checks; skip per-source matrix probes.",
    )
    parser.add_argument(
        "--surface-only",
        action="store_true",
        help=(
            "Only verify health/readiness/docs/panel and admin API surface; "
            "skip mutating backend/WARP and external zero-key capability probes."
        ),
    )
    parser.add_argument(
        "--allow-locked-admin",
        action="store_true",
        help="Do not fail if admin endpoints are locked; admin-dependent checks are skipped.",
    )
    parser.add_argument(
        "--no-require-openapi",
        action="store_true",
        help="Do not require /openapi.json to be exposed.",
    )
    parser.add_argument(
        "--no-require-warp",
        action="store_true",
        help="Record WARP failures without failing the workflow.",
    )
    parser.add_argument(
        "--min-default-paper-no-warp",
        type=int,
        default=int(os.environ.get("SOUWEN_SMOKE_MIN_DEFAULT_PAPER_NO_WARP", "4")),
    )
    parser.add_argument(
        "--min-default-paper-warp",
        type=int,
        default=int(os.environ.get("SOUWEN_SMOKE_MIN_DEFAULT_PAPER_WARP", "5")),
    )
    parser.add_argument(
        "--min-best-web-engines",
        type=int,
        default=int(os.environ.get("SOUWEN_SMOKE_MIN_BEST_WEB_ENGINES", "1")),
    )
    return parser.parse_args(argv)


def parse_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or list(default)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config = SmokeConfig(
        base_url=normalize_base_url(args.base_url),
        expected_version=args.expected_version,
        request_timeout=args.request_timeout,
        bearer_token=args.bearer_token,
        warp_modes=parse_csv(args.warp_modes, DEFAULT_WARP_MODES),
        require_admin=not args.allow_locked_admin,
        require_openapi=not args.no_require_openapi,
        require_warp=not args.no_require_warp,
        full_matrix=not args.quick_matrix,
        min_default_paper_no_warp=args.min_default_paper_no_warp,
        min_default_paper_warp=args.min_default_paper_warp,
        min_best_web_engines=args.min_best_web_engines,
        surface_only=args.surface_only,
    )
    results = run_report(config)
    print_console_report(results)

    report = build_markdown_report(config, results)
    write_text(args.report_file, report)
    write_text(args.summary_file, report, append=True)
    write_json(args.json_file, results)

    failures = required_failures(results)
    if failures:
        print(
            f"HF Space CD test failed: {len(failures)} required check(s) failed.", file=sys.stderr
        )
        return 1
    print("HF Space CD test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
