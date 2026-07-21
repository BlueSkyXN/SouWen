"""Manual anonymous ERIC functional smoke.

The script is intentionally outside ordinary pytest.  It sends one official,
anonymous ERIC metadata search only when ``--mode live --execute`` is explicit.
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


DEFAULT_QUERY = "education"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_eric_registered() -> tuple[str, dict[str, object]]:
    from souwen.registry import get

    adapter = get("eric")
    require(adapter is not None, "source 'eric' is not registered")
    require(adapter.domain == "paper", f"unexpected ERIC domain: {adapter.domain!r}")
    require("search" in adapter.capabilities, "ERIC search capability is missing")
    require(adapter.resolved_needs_config is False, "ERIC must remain anonymously available")
    return (
        "eric registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "needs_config": adapter.resolved_needs_config,
        },
    )


async def run_eric_search(
    *,
    query: str,
    rows: int,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[str, dict[str, object]]:
    if client_factory is None:
        from souwen.paper.eric import EricClient

        client_factory = EricClient

    async with client_factory() as client:
        response = await client.search(query, rows=rows)

    require(response.source == "eric", f"unexpected source: {response.source!r}")
    require(response.results, "ERIC returned no results for the live smoke query")
    first = response.results[0]
    require(first.source == "eric", f"unexpected result source: {first.source!r}")
    require(bool(first.title), "first ERIC result has no title")
    require(bool(first.source_url), "first ERIC result has no source_url")
    return (
        f"ERIC search returned {len(response.results)} result(s)",
        {
            "query": query,
            "rows": rows,
            "returned": len(response.results),
            "first_title": first.title,
            "first_url": first.source_url,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; ERIC live query was not sent",
        )
        return

    await run_check(
        recorder, "eric_registry", verify_eric_registered, required=True, timeout=args.timeout
    )
    await run_check(
        recorder,
        "eric_anonymous_live_search",
        lambda: run_eric_search(query=args.query, rows=args.rows),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run one explicit anonymous ERIC live smoke.")
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="ERIC search query.")
    parser.add_argument(
        "--rows", type=int, default=1, help="Result count for the single request (1..10)."
    )
    args = parser.parse_args(argv)
    if not 1 <= args.rows <= 10:
        parser.error("--rows must be within 1..10")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="eric_functional_check",
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
