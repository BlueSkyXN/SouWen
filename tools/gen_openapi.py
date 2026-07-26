#!/usr/bin/env python3
"""Generate and validate the canonical target-only OpenAPI artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from souwen.delivery.api.openapi_artifact import (
    TARGET_OPENAPI_VERSION,
    build_target_openapi_document,
    canonical_openapi_bytes,
    semantic_diff_openapi,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = (
    REPOSITORY_ROOT / "contracts" / "openapi" / f"souwen-openapi-{TARGET_OPENAPI_VERSION}.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--write", action="store_true", help="write the materialized artifact")
    actions.add_argument(
        "--check", action="store_true", help="verify the checked artifact byte-for-byte"
    )
    actions.add_argument(
        "--semantic-check",
        type=Path,
        metavar="BASELINE",
        help="compare BASELINE with the current canonical candidate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ARTIFACT,
        help="artifact destination for --write or checked path for --check",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        help="write the semantic report as deterministic JSON",
    )
    return parser


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    candidate = build_target_openapi_document()
    payload = canonical_openapi_bytes(candidate)

    if args.write:
        _write_bytes(args.output, payload)
        print(f"wrote {args.output}")
        return 0

    if args.check:
        if not args.output.is_file():
            print(f"missing canonical OpenAPI artifact: {args.output}", file=sys.stderr)
            return 1
        if args.output.read_bytes() != payload:
            print(f"canonical OpenAPI artifact is stale: {args.output}", file=sys.stderr)
            return 1
        print(f"canonical OpenAPI artifact is reproducible: {args.output}")
        return 0

    baseline_path = args.semantic_check
    if baseline_path is None or not baseline_path.is_file():
        print(f"missing semantic baseline: {baseline_path}", file=sys.stderr)
        return 2
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid semantic baseline {baseline_path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(baseline, dict):
        print(f"invalid semantic baseline {baseline_path}: root must be an object", file=sys.stderr)
        return 2
    report = semantic_diff_openapi(baseline, candidate)
    report_payload = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if args.json_report is not None:
        _write_bytes(args.json_report, report_payload)
    print(report_payload.decode("utf-8"))
    return 1 if report["breaking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
