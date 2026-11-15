#!/usr/bin/env python3
"""Classify a WARP leg report instead of trusting the probe's exit code alone.

The workflow keeps the probe's exit code and the report JSON, then hands the
report here. Only one outcome may be recorded as "unverified": the external
WARP registration/egress probe (``warp.socks_egress``) failing while the
manager itself reports no implementation error. Everything else fails the job:

- a missing, corrupt or incomplete report,
- required browser/HTTP/MCP content failures after the proxy came up,
- an implementation error (AttributeError & co) recorded by the manager —
  ``usque`` was once exactly this, and it must never read as "the network
  was unavailable".

Exit code: 0 for PASS or UNVERIFIED, 1 for FAIL.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VERDICT_PASS = "PASS"
VERDICT_UNVERIFIED = "UNVERIFIED"
VERDICT_FAIL = "FAIL"

EXTERNAL_EGRESS_CHECK = "warp.socks_egress"
WARP_CHECKS = (
    EXTERNAL_EGRESS_CHECK,
    "warp.exit_differs",
    # 实际模式是必验项：推荐模式不等于实际跑的路径（usque 曾推荐但方法缺失，
    # 代理只在回退 wireproxy 后才起来）。
    "warp.actual_mode",
    "warp.browser_via_warp",
    "warp.mcp_after_warp",
    "warp.http_after_warp",
)

USQUE_EGRESS_CHECK = "usqueforced.socks_egress"
# 第一个元素是外部出口探针，classify_warp_report 依赖这个约定。
USQUE_CHECKS = (
    USQUE_EGRESS_CHECK,
    "usqueforced.mode_requested",
    "usqueforced.actual_mode",
    "usqueforced.browser_via_usque",
)


def _state_implementation_error(check: dict[str, Any]) -> bool:
    details = check.get("details") or {}
    state = details.get("warp_state") or {}
    return bool(state.get("implementation_error"))


def classify_warp_report(report: Any, *, expected_checks: tuple[str, ...]) -> tuple[str, str]:
    """Return (verdict, reason) for one WARP leg report.

    ``expected_checks[0]`` is the external egress probe; its failure may be
    recorded as unverified (unless the manager says implementation error),
    every other failure fails the job.
    """

    if not isinstance(report, dict) or not isinstance(report.get("checks"), list):
        return VERDICT_FAIL, "WARP report is missing or corrupt; the probe result cannot be judged"

    checks: dict[str, dict[str, Any]] = {}
    for item in report["checks"]:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            checks[item["name"]] = item

    missing = [name for name in expected_checks if name not in checks]
    if missing:
        return VERDICT_FAIL, f"WARP report is incomplete; missing checks: {', '.join(missing)}"

    egress = checks[expected_checks[0]]
    if egress.get("outcome") == "FAIL":
        if _state_implementation_error(egress):
            state = (egress.get("details") or {}).get("warp_state") or {}
            return VERDICT_FAIL, (
                "WARP manager recorded an implementation error "
                f"({state.get('last_error')!r}); this is a defect, not an "
                "environment problem"
            )
        history = (egress.get("details") or {}).get("history") or []
        state = (egress.get("details") or {}).get("warp_state") or {}
        last_error = state.get("last_error") or "not recorded"
        return VERDICT_UNVERIFIED, (
            "external WARP registration/egress never came up "
            f"({len(history)} recorded attempt(s), manager last_error: {last_error!r}); "
            "the WARP-dependent checks are reported as unverified, not passed"
        )

    # 这些检查都是必验项：SKIP / WARN 也等于"没有验证通过"，不能算 PASS。
    # 上一轮就出现过 actual_mode 因状态文件未落盘而 SKIP、整腿仍记 PASS 的情况。
    failures = [
        f"{name}={check.get('outcome')}"
        for name, check in checks.items()
        if check.get("outcome") != "PASS"
    ]
    if failures:
        return VERDICT_FAIL, (
            "required WARP checks did not pass after the proxy came up: " + ", ".join(failures)
        )

    return VERDICT_PASS, "all WARP checks passed"


def classify(report: Any, *, kind: str) -> tuple[str, str]:
    expected = WARP_CHECKS if kind == "warp" else USQUE_CHECKS
    verdict, reason = classify_warp_report(report, expected_checks=expected)
    if kind == "usque-forced" and verdict == VERDICT_UNVERIFIED:
        reason += (
            "; usque itself remains unproven — record the actual mode and error, do not claim usage"
        )
    return verdict, reason


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--kind", choices=("warp", "usque-forced"), default="warp")
    parser.add_argument("--summary-file", type=Path, default=None)
    args = parser.parse_args(argv)

    report: Any = None
    try:
        report = json.loads(args.json_report.read_text(encoding="utf-8"))
    except FileNotFoundError:
        report = None
    except (UnicodeDecodeError, json.JSONDecodeError):
        report = None

    verdict, reason = classify(report, kind=args.kind)
    lines = [
        f"WARP leg verdict ({args.kind}): **{verdict}**",
        "",
        reason,
    ]
    text = "\n".join(lines)
    print(text)
    if args.summary_file is not None:
        with args.summary_file.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    if verdict == VERDICT_FAIL:
        print(f"::error::WARP leg ({args.kind}) FAILED: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
