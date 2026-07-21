#!/usr/bin/env python3
"""Explicit, single-attempt functional evidence for one UniAPI Ark search source.

The default ``dry-run`` mode has no network dependency and can run without
credentials.  A live check is intentionally opt-in: it needs both
``--mode live`` and ``--execute``, uses exactly the selected concrete source,
and never retries or switches models after a failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover - direct script execution.
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check

from souwen.core.redaction import redact_secret_payload, redact_secret_text
from souwen.registry import get as get_source_adapter


ARK_SOURCES = (
    "uniapi_ark_annotations_deepseek_v3_2_251201",
    "uniapi_ark_annotations_doubao_seed_2_0_lite_260428",
)
DEFAULT_QUERY = "OpenAI official research"
_REPORT_OMIT_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "base_url",
        "request_id",
        "response_id",
        "encrypted_content",
        "raw",
        "raw_response",
    }
)
_REPORT_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)\b(?P<key>base[_-]?url|request[_-]?id|response[_-]?id|encrypted[_-]?content)"
    r"(?P<separator>\s*[:=]\s*)[^\s,;\]\}\"']+"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _safe_report_value(value: object) -> object:
    """Remove credentials, private gateway data and opaque provider material."""
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            normalized_key = str(key)
            if normalized_key.lower() in _REPORT_OMIT_KEYS:
                continue
            sanitized[normalized_key] = _safe_report_value(item)
        return sanitized
    if isinstance(value, list | tuple):
        return [_safe_report_value(item) for item in value]
    if isinstance(value, str):
        redacted = redact_secret_text(value) or ""
        return _REPORT_SENSITIVE_TEXT_RE.sub(
            lambda match: f"{match.group('key')}{match.group('separator')}***", redacted
        )
    return redact_secret_payload(value)


def _write_sanitized_reports(
    recorder: ResultRecorder,
    *,
    json_report: Path | None,
    markdown_report: Path | None,
) -> None:
    """Write reports without retaining error tracebacks or secret-bearing details."""
    payload = _safe_report_value(recorder.to_json())
    assert isinstance(payload, dict)
    if json_report is not None:
        json_report.parent.mkdir(parents=True, exist_ok=True)
        json_report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if markdown_report is not None:
        markdown_report.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# UniAPI Search Functional Check",
            "",
            f"Overall: **{payload['overall']}**",
            "",
            "| Check | Required | Outcome | Duration | Message |",
            "|---|---:|---|---:|---|",
        ]
        for item in payload["checks"]:
            assert isinstance(item, dict)
            lines.append(
                "| {name} | {required} | {outcome} | {duration:.3f}s | {message} |".format(
                    name=str(item["name"]).replace("|", "\\|"),
                    required="yes" if item["required"] else "no",
                    outcome=item["outcome"],
                    duration=float(item["duration_seconds"]),
                    message=str(item["message"]).replace("|", "\\|").replace("\n", " "),
                )
            )
        lines.extend(
            [
                "",
                "## JSON Summary",
                "",
                "```json",
                json.dumps(payload, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
        markdown_report.write_text("\n".join(lines), encoding="utf-8")


def verify_ark_source_contract(source_id: str) -> tuple[str, dict[str, object]]:
    """Verify the selected immutable source without importing its client or sending traffic."""
    adapter = get_source_adapter(source_id)
    require(adapter is not None, f"source {source_id!r} is not registered")
    require(adapter.domain == "web", f"unexpected source domain: {adapter.domain!r}")
    require("search" in adapter.capabilities, "selected source has no search capability")
    require(adapter.llm_search_identity is not None, "selected source lacks immutable LLM identity")
    scheme_id, model_id = adapter.llm_search_identity
    require(scheme_id == "uniapi_ark_annotations_v1", f"unexpected scheme: {scheme_id!r}")
    require(bool(model_id), "selected source has no exact model ID")
    require(
        adapter.runtime_default_enabled is False, "Ark live sources must remain explicit opt-in"
    )
    return (
        "selected UniAPI Ark source contract passed",
        {
            "source_id": source_id,
            "scheme_id": scheme_id,
            "requested_model_id": model_id,
            "endpoint_type": "responses",
            "tool_schema": "ark_web_search_v1",
            "candidate_contract": "structured_result_list",
            "runtime_default_enabled": adapter.runtime_default_enabled,
        },
    )


async def run_single_source_live_smoke(
    *,
    source_id: str,
    query: str,
    max_results: int,
    fetch_provider: str,
    timeout: float,
    expected_url: str | None = None,
    fetcher: Callable[..., Any] | None = None,
) -> tuple[str, dict[str, object]]:
    """Make exactly one bound search request, then one bounded safe fetch batch."""
    adapter = get_source_adapter(source_id)
    require(adapter is not None, f"source {source_id!r} is not registered")
    client_cls = adapter.client_loader()
    try:
        async with client_cls() as client:
            receipt = await client.search_candidate_receipt(query, max_results=max_results)
        candidates = list(receipt.candidates)
        require(candidates, "selected source returned no strict candidates")
        if expected_url is not None:
            require(
                expected_url in {candidate.url for candidate in candidates},
                "expected URL was absent from structured candidates",
            )
        if fetcher is None:
            from souwen.web.fetch import fetch_content

            fetcher = fetch_content
        urls = [candidate.url for candidate in candidates]
        fetched = await fetcher(
            urls,
            providers=[fetch_provider],
            strategy="fallback",
            timeout=timeout,
            max_length=4_000,
        )
        usable = next(
            (
                item
                for item in fetched.results
                if item.error is None and bool(item.title.strip()) and bool(item.content.strip())
            ),
            None,
        )
        require(usable is not None, "no fetched candidate supplied title and page content")
    except Exception:
        # The common recorder would otherwise serialize a provider traceback,
        # which can include credentials or a private gateway endpoint.
        raise RuntimeError(
            "selected UniAPI source did not meet the live functional contract"
        ) from None

    first = candidates[0]
    return (
        "single bound UniAPI search and bounded fetch completed",
        {
            "source_id": source_id,
            "scheme_id": first.provenance.scheme_id,
            "endpoint_type": "responses",
            "requested_model_id": first.provenance.requested_model_id,
            "served_model_id": first.provenance.served_model_id,
            "response_status": receipt.response_status,
            "tool_call_types": list(receipt.tool_call_types),
            "valid_annotation_count": receipt.valid_annotation_count,
            "candidate_count": len(candidates),
            "visible_search_calls": receipt.visible_search_calls,
            "provider_metered_search_calls": receipt.provider_metered_search_calls,
            "input_tokens": receipt.input_tokens,
            "output_tokens": receipt.output_tokens,
            "total_tokens": receipt.total_tokens,
            "fetch_provider": usable.source,
            "fetch_status": "success",
            "fetched_title_present": bool(usable.title.strip()),
            "extractive_excerpt_chars": min(len(usable.content.strip()), 500),
            "expected_url_matched": expected_url is not None,
            "search_request_attempts": 1,
            "automatic_model_fallback": False,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    await run_check(
        recorder,
        "uniapi_ark_registry_contract",
        lambda: verify_ark_source_contract(args.source),
        required=True,
        timeout=args.timeout,
    )
    if args.mode == "dry-run":
        recorder.record(
            "live_execution",
            Outcome.SKIP,
            required=False,
            message="dry-run requested; no UniAPI or fetch request was sent",
            details={"source_id": args.source, "search_request_attempts": 0},
        )
        return
    await run_check(
        recorder,
        "single_bound_search_and_fetch",
        lambda: run_single_source_live_smoke(
            source_id=args.source,
            query=args.query,
            max_results=args.max_results,
            fetch_provider=args.fetch_provider,
            timeout=args.timeout,
            expected_url=args.expected_url,
        ),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, default_mode="dry-run", modes=("dry-run", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on a live contract failure.")
    parser.add_argument("--source", choices=ARK_SOURCES, required=True)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument("--fetch-provider", default="builtin")
    parser.add_argument("--expected-url", default=None)
    args = parser.parse_args(argv)
    if not 1 <= args.max_results <= 10:
        parser.error("--max-results must be within 1..10")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="uniapi_search_functional_check",
        mode=args.mode,
        environment={
            "source_id": args.source,
            "live_execution_confirmed": bool(args.execute),
            "required_live_failures": bool(args.required),
            "automatic_retry": False,
            "automatic_model_fallback": False,
        },
    )
    try:
        await run_selected_checks(args, recorder)
    finally:
        try:
            _write_sanitized_reports(
                recorder, json_report=args.json_report, markdown_report=args.markdown_report
            )
        except Exception as exc:  # noqa: BLE001 - report failures have a stable exit code.
            print(f"failed to write functional check reports: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc

    for check in recorder.checks:
        print(f"{check.outcome.value} {check.name}: {check.message}")
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
