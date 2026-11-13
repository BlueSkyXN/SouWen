#!/usr/bin/env python3
"""Zero-key source census client.

Sends fixed search/fetch requests to a running SouWen instance and records
per-source, per-domain and per-URL outcomes as PASS / WARN / FAIL / SKIP.
This script intentionally lives outside ordinary pytest: it exercises the
live network path through the server under test.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_QUERIES_PATH = Path(__file__).resolve().parent / "census" / "queries.json"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MIN_INTERVAL_SECONDS = 1.15  # stay under the server's 60 req/min limiter

# Markers that indicate a fetch returned an interstitial rather than content.
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


@dataclass(slots=True)
class ProbeOutcome:
    """One query-level observation."""

    label: str  # source id, domain name, or URL index
    query: str  # literal query or URL
    valid: bool
    result_count: int = 0
    http_status: int | None = None
    error: str = ""
    duration_seconds: float = 0.0
    served_by: list[str] = field(default_factory=list)
    category: str = ""  # fetch URL category: static | js | anticrawl


@dataclass(slots=True)
class SourceVerdict:
    """SPEC 6.3 verdict for one source or domain aggregate."""

    label: str
    outcome: str  # PASS | WARN | FAIL | SKIP
    valid_count: int
    total: int
    detail: str

    @property
    def rate(self) -> str:
        return f"{self.valid_count}/{self.total}"


def is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def count_valid_search_items(payload: Any) -> tuple[int, int]:
    """Return (valid_item_count, total_item_count) for an agent /search payload."""

    items = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return 0, 0
    valid = sum(
        1
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("title"), str)
        and item["title"].strip()
        and is_http_url(item.get("url"))
    )
    return valid, len(items)


def search_query_valid(payload: Any, *, min_results: int) -> bool:
    valid, _total = count_valid_search_items(payload)
    return valid >= min_results


def fetch_content_success(payload: Any, *, min_chars: int) -> bool:
    """Judge one agent /fetch payload for a single URL."""

    if not isinstance(payload, dict):
        return False
    content = payload.get("content")
    if not isinstance(content, str) or len(content.strip()) < min_chars:
        return False
    haystack = f"{payload.get('title') or ''}\n{content[:4000]}".lower()
    return not any(marker in haystack for marker in VERIFICATION_MARKERS)


def verdict_from_counts(label: str, valid_count: int, total: int, *, detail: str) -> SourceVerdict:
    if total <= 0:
        return SourceVerdict(label, "SKIP", 0, 0, "no probes ran")
    if valid_count >= 2:
        outcome = "PASS"
    elif valid_count == 1:
        outcome = "WARN"
    else:
        outcome = "FAIL"
    return SourceVerdict(label, outcome, valid_count, total, detail)


class CensusError(RuntimeError):
    pass


class Client:
    """Minimal JSON HTTP client with edge/app token split like hf_space_smoke."""

    def __init__(
        self,
        base_url: str,
        *,
        edge_token: str | None,
        app_token: str | None,
        timeout: float,
        min_interval: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.edge_token = edge_token
        self.app_token = app_token
        self.timeout = timeout
        self.min_interval = min_interval
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self.min_interval - (now - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def json_request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        max_attempts: int = 2,
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json", "User-Agent": "SouWen-Census/1"}
        if self.edge_token:
            headers["Authorization"] = f"Bearer {self.edge_token}"
            if self.app_token:
                headers["X-SouWen-Token"] = self.app_token
        elif self.app_token:
            headers["Authorization"] = f"Bearer {self.app_token}"
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        for attempt in range(1, max_attempts + 1):
            self._throttle()
            request = urllib.request.Request(
                f"{self.base_url}{path}", data=body, headers=headers, method=method
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.status, _parse_json(response.read())
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                if exc.code == 429 and attempt < max_attempts:
                    retry_after = _retry_after_seconds(exc.headers.get("Retry-After"))
                    time.sleep(retry_after or 65.0)
                    continue
                return exc.code, _parse_json(raw)
            except urllib.error.URLError as exc:
                reason = getattr(exc, "reason", exc)
                raise CensusError(f"request failed: {type(reason).__name__}") from exc
        raise CensusError("request attempts exhausted")


def _parse_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _error_code(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("code", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str):
                return value[:120]
            if isinstance(value, dict) and isinstance(value.get("code"), str):
                return value["code"][:120]
    return "unknown"


def run_search_probe(
    client: Client,
    *,
    query: str,
    domain: str,
    provider: str | None,
    page_limit: int,
    min_results: int,
) -> ProbeOutcome:
    payload_body: dict[str, Any] = {"query": query, "domain": domain, "limit": page_limit}
    if provider is not None:
        payload_body["providers"] = [provider]
    started = time.perf_counter()
    outcome = ProbeOutcome(label="", query=query, valid=False)
    try:
        status, payload = client.json_request("/search", method="POST", payload=payload_body)
    except CensusError as exc:
        outcome.error = str(exc)
        outcome.duration_seconds = time.perf_counter() - started
        return outcome
    outcome.http_status = status
    outcome.duration_seconds = time.perf_counter() - started
    if status != 200:
        outcome.error = _error_code(payload)
        return outcome
    outcome.valid = search_query_valid(payload, min_results=min_results)
    outcome.result_count = count_valid_search_items(payload)[0]
    served = payload.get("sources") if isinstance(payload, dict) else None
    if isinstance(served, list):
        outcome.served_by = [str(item) for item in served]
    if not outcome.valid and not outcome.error:
        outcome.error = f"only {outcome.result_count} valid items"
    return outcome


def run_fetch_probe(
    client: Client,
    *,
    url: str,
    provider: str | None,
    min_chars: int,
) -> ProbeOutcome:
    # max_chars 放宽到接口上限：分页读取下 500 字判定需要接近全文的窗口。
    payload_body: dict[str, Any] = {"url": url, "max_chars": 200_000}
    if provider is not None:
        payload_body["provider"] = provider
    started = time.perf_counter()
    outcome = ProbeOutcome(label="", query=url, valid=False)
    try:
        status, payload = client.json_request("/fetch", method="POST", payload=payload_body)
    except CensusError as exc:
        outcome.error = str(exc)
        outcome.duration_seconds = time.perf_counter() - started
        return outcome
    outcome.http_status = status
    outcome.duration_seconds = time.perf_counter() - started
    if status != 200:
        outcome.error = _error_code(payload)
        return outcome
    outcome.valid = fetch_content_success(payload, min_chars=min_chars)
    content = payload.get("content") if isinstance(payload, dict) else None
    outcome.result_count = len(content) if isinstance(content, str) else 0
    if not outcome.valid and not outcome.error:
        outcome.error = f"content {outcome.result_count} chars"
    return outcome


def select_queries(
    queries: dict[str, Any], mode: str, only: list[str] | None
) -> list[dict[str, Any]]:
    """Build the probe plan: one entry per (target, query/url) pair."""

    plan: list[dict[str, Any]] = []
    page_limit = int(queries.get("search_page_limit", 5))
    min_results = int(queries.get("min_valid_results", 3))
    min_chars = int(queries.get("min_fetch_chars", 500))
    only_set = set(only) if only else None

    if mode == "sources":
        for source_id, meta in sorted(queries["sources"].items()):
            if only_set is not None and source_id not in only_set:
                continue
            if meta["kind"] == "search":
                domain_queries = queries["domains"][meta["domain"]][:3]
                for query in domain_queries:
                    plan.append(
                        {
                            "kind": "search",
                            "target": source_id,
                            "provider": source_id,
                            "domain": meta["domain"],
                            "query": query,
                            "page_limit": page_limit,
                            "min_results": min_results,
                        }
                    )
            elif meta["kind"] == "fetch":
                urls = queries["fetch_source_probes"].get(source_id, [])
                for url in urls:
                    plan.append(
                        {
                            "kind": "fetch",
                            "target": source_id,
                            "provider": source_id,
                            "query": url,
                            "min_chars": min_chars,
                        }
                    )
            else:
                raise CensusError(f"unsupported kind for source {source_id}: {meta['kind']}")
    elif mode == "domains":
        for domain in queries["census_domains"]:
            for query in queries["domains"][domain]:
                plan.append(
                    {
                        "kind": "search",
                        "target": domain,
                        "provider": None,
                        "domain": domain,
                        "query": query,
                        "page_limit": page_limit,
                        "min_results": min_results,
                    }
                )
    elif mode == "fetch":
        for category in ("static", "js", "anticrawl"):
            for index, url in enumerate(queries["fetch_urls"][category]):
                plan.append(
                    {
                        "kind": "fetch",
                        "target": f"{category}[{index}]",
                        "provider": None,
                        "query": url,
                        "min_chars": min_chars,
                        "category": category,
                    }
                )
    else:
        raise CensusError(f"unknown mode: {mode}")
    return plan


def run_plan(client: Client, plan: list[dict[str, Any]]) -> list[ProbeOutcome]:
    outcomes: list[ProbeOutcome] = []
    for entry in plan:
        if entry["kind"] == "search":
            outcome = run_search_probe(
                client,
                query=entry["query"],
                domain=entry["domain"],
                provider=entry["provider"],
                page_limit=entry["page_limit"],
                min_results=entry["min_results"],
            )
        else:
            outcome = run_fetch_probe(
                client,
                url=entry["query"],
                provider=entry["provider"],
                min_chars=entry["min_chars"],
            )
        outcome.label = entry["target"]
        outcome.category = entry.get("category", "")
        outcomes.append(outcome)
        marker = "ok " if outcome.valid else "MISS"
        print(
            f"[{marker}] {entry['target']} :: {entry['query'][:60]} :: "
            f"{outcome.error or f'{outcome.result_count} results'}",
            file=sys.stderr,
        )
    return outcomes


def aggregate(outcomes: list[ProbeOutcome]) -> list[SourceVerdict]:
    verdicts: list[SourceVerdict] = []
    grouped: dict[str, list[ProbeOutcome]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome.label, []).append(outcome)
    for label in sorted(grouped):
        group = grouped[label]
        valid = sum(1 for item in group if item.valid)
        errors = "; ".join(
            dict.fromkeys(item.error for item in group if not item.valid and item.error)
        )[:200]
        detail = errors or (
            f"{valid}/{len(group)} valid" if valid < len(group) else "all probes valid"
        )
        verdicts.append(verdict_from_counts(label, valid, len(group), detail=detail))
    return verdicts


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SouWen census",
        "",
        f"- Overall: **{report['overall']}**",
        f"- Mode: `{report['mode']}` / label: `{report['label']}`",
        f"- Base URL: `{report['base_url']}`",
        f"- Started: {report['started_at']} (duration {report['duration_seconds']:.0f}s)",
        "",
        "| Target | Outcome | Valid | Detail |",
        "|---|---|---|---|",
    ]
    for verdict in report["verdicts"]:
        lines.append(
            f"| `{verdict['label']}` | {verdict['outcome']} | "
            f"{verdict['valid_count']}/{verdict['total']} | {_cell(verdict['detail'])} |"
        )
    lines.extend(["", "## Per-probe outcomes", ""])
    for outcome in report["probes"]:
        status = "valid" if outcome["valid"] else "invalid"
        lines.append(
            f"- `{outcome['label']}` `{status}` `{outcome['query'][:80]}` "
            f"http={outcome['http_status']} {outcome.get('error', '')}"
        )
    return "\n".join(lines) + "\n"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_report(
    *,
    mode: str,
    label: str,
    base_url: str,
    outcomes: list[ProbeOutcome],
) -> dict[str, Any]:
    verdicts = aggregate(outcomes)
    ordered = {"FAIL": 0, "WARN": 1, "PASS": 2, "SKIP": 3}
    verdicts.sort(key=lambda item: (ordered[item.outcome], item.label))
    if any(item.outcome == "FAIL" for item in verdicts):
        overall = "FAIL"
    elif any(item.outcome == "WARN" for item in verdicts):
        overall = "WARN"
    elif verdicts:
        overall = "PASS"
    else:
        overall = "SKIP"
    return {
        "schema_version": 1,
        "script": "census",
        "mode": mode,
        "label": label,
        "base_url": base_url.rstrip("/"),
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "overall": overall,
        "duration_seconds": 0.0,
        "verdicts": [asdict(item) for item in verdicts],
        "probes": [asdict(item) for item in outcomes],
    }


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--bearer-token", default=None)
    parser.add_argument("--hf-space-token", default=None)
    parser.add_argument("--mode", required=True, choices=("sources", "domains", "fetch"))
    parser.add_argument("--only", default=None, help="Comma-separated source ids (sources mode)")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--label", default="", help="Environment label recorded in the report")
    parser.add_argument("--json-file", type=Path, default=None)
    parser.add_argument("--markdown-report", type=Path, default=None)
    parser.add_argument("--request-timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--min-interval", type=float, default=DEFAULT_MIN_INTERVAL_SECONDS)
    parser.add_argument(
        "--summary-file",
        default=None,
        help="Append the markdown report to this file (e.g. GITHUB_STEP_SUMMARY)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    queries = json.loads(args.queries.read_text(encoding="utf-8"))
    only = [item.strip() for item in args.only.split(",")] if args.only else None
    plan = select_queries(queries, args.mode, only)
    if not plan:
        print("no probes selected; check --mode/--only", file=sys.stderr)
        return 2
    client = Client(
        args.base_url,
        edge_token=args.hf_space_token,
        app_token=args.bearer_token,
        timeout=args.request_timeout,
        min_interval=args.min_interval,
    )
    started = time.perf_counter()
    outcomes = run_plan(client, plan)
    report = build_report(
        mode=args.mode,
        label=args.label,
        base_url=args.base_url,
        outcomes=outcomes,
    )
    report["duration_seconds"] = round(time.perf_counter() - started, 1)
    markdown = render_markdown(report)
    if args.json_file:
        args.json_file.parent.mkdir(parents=True, exist_ok=True)
        args.json_file.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if args.markdown_report:
        args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_report.write_text(markdown, encoding="utf-8")
    if args.summary_file:
        with Path(args.summary_file).open("a", encoding="utf-8") as handle:
            handle.write(markdown)
    counts: dict[str, int] = {}
    for verdict in report["verdicts"]:
        counts[verdict["outcome"]] = counts.get(verdict["outcome"], 0) + 1
    print(
        f"census {args.mode} [{args.label}]: overall={report['overall']} "
        + " ".join(f"{key}={value}" for key, value in sorted(counts.items())),
        file=sys.stderr,
    )
    # 判定结果是体检数据而非门禁失败：sources/domains/fetch 的 FAIL 由
    # 报告与进度表承载；脚本崩溃、参数错误、报告未写出才让 CI 变红。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
