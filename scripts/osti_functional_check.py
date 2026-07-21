#!/usr/bin/env python3
"""Manual anonymous OSTI.GOV functional smoke.

The script sends exactly one official search plus one detail request only when
``--mode live --execute`` is explicit.  It remains outside ordinary pytest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from typing import Any

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/...` execution.
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check


DEFAULT_QUERY = "machine learning"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_osti_registered() -> tuple[str, dict[str, object]]:
    from souwen.registry import get

    adapter = get("osti")
    require(adapter is not None, "source 'osti' is not registered")
    require(adapter.domain == "paper", f"unexpected OSTI domain: {adapter.domain!r}")
    require({"search", "get_detail"} <= adapter.capabilities, "OSTI capabilities are incomplete")
    require(adapter.resolved_needs_config is False, "OSTI must remain anonymously available")
    return (
        "OSTI registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "needs_config": adapter.resolved_needs_config,
        },
    )


async def run_osti_search_and_detail(
    *,
    query: str,
    rows: int,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[str, dict[str, object]]:
    if client_factory is None:
        from souwen.paper.osti import OstiClient

        client_factory = OstiClient

    async with client_factory() as client:
        response = await client.search(query, rows=rows)
        require(response.source == "osti", f"unexpected source: {response.source!r}")
        require(response.results, "OSTI returned no results for the live smoke query")
        first = response.results[0]
        osti_id = first.raw.get("osti_id")
        require(isinstance(osti_id, str) and osti_id, "first OSTI result has no osti_id")
        detail = await client.get_by_id(osti_id)

    require(detail.source == "osti", f"unexpected detail source: {detail.source!r}")
    require(detail.raw.get("osti_id") == osti_id, "detail record ID does not match search result")
    require(bool(detail.title), "OSTI detail has no title")
    return (
        f"OSTI search/detail returned record {osti_id}",
        {
            "query": query,
            "rows": rows,
            "returned": len(response.results),
            "osti_id": osti_id,
            "first_title": detail.title,
            "first_url": detail.source_url,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; OSTI live requests were not sent",
        )
        return

    await run_check(
        recorder, "osti_registry", verify_osti_registered, required=True, timeout=args.timeout
    )
    await run_check(
        recorder,
        "osti_anonymous_live_search_and_detail",
        lambda: run_osti_search_and_detail(query=args.query, rows=args.rows),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run explicit anonymous OSTI search/detail smoke.")
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="OSTI search query.")
    parser.add_argument("--rows", type=int, default=1, help="Result count for the single search.")
    args = parser.parse_args(argv)
    if args.rows < 1:
        parser.error("--rows must be greater than or equal to 1")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="osti_functional_check",
        mode=args.mode,
        environment={
            "live_execution_confirmed": bool(args.execute),
            "required_live_failures": bool(args.required),
        },
    )
    try:
        await run_selected_checks(args, recorder)
    finally:
        try:
            recorder.write_reports(
                json_report=args.json_report,
                markdown_report=args.markdown_report,
            )
        except Exception as exc:  # noqa: BLE001 - report write failures have a fixed exit code.
            print(f"failed to write functional check reports: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc

    for check in recorder.checks:
        print(f"{check.outcome.value} {check.name}: {check.message}")
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
