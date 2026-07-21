"""Manual anonymous OpenAlex functional smoke.

This check deliberately stays outside ordinary pytest and is never scheduled
from a pull request.  ``--mode live --execute`` sends one anonymous query to
the official OpenAlex API so maintainers can collect timestamped evidence
without using a configured API key or replaying a metered request.
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


DEFAULT_QUERY = "open science"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_openalex_registered() -> tuple[str, dict[str, object]]:
    """Confirm the live script targets the canonical optional-key source."""
    from souwen.registry import get

    adapter = get("openalex")
    require(adapter is not None, "source 'openalex' is not registered")
    require(adapter.domain == "paper", f"unexpected OpenAlex domain: {adapter.domain!r}")
    require("search" in adapter.capabilities, "OpenAlex search capability is missing")
    require(adapter.config_field == "openalex_api_key", "OpenAlex config_field drifted")
    require(adapter.resolved_needs_config is False, "OpenAlex must remain anonymously available")
    return (
        "openalex registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "config_field": adapter.config_field,
            "needs_config": adapter.resolved_needs_config,
        },
    )


async def run_anonymous_openalex_search(
    *,
    query: str,
    per_page: int,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[str, dict[str, object]]:
    """Run one search after clearing any configured key from the client instance."""
    if client_factory is None:
        from souwen.paper.openalex import OpenAlexClient

        client_factory = OpenAlexClient

    client = client_factory()
    # A maintainer may have a key in a local config file.  The manual smoke is
    # intentionally anonymous, so it must never send that credential upstream.
    if hasattr(client, "api_key"):
        client.api_key = None

    async with client:
        response = await client.search(query, per_page=per_page)

    require(response.source == "openalex", f"unexpected source: {response.source!r}")
    require(response.results, "OpenAlex returned no results for the live smoke query")
    first = response.results[0]
    require(first.source == "openalex", f"unexpected result source: {first.source!r}")
    require(bool(first.title), "first OpenAlex result has no title")
    require(bool(first.source_url), "first OpenAlex result has no source_url")
    return (
        f"anonymous OpenAlex search returned {len(response.results)} result(s)",
        {
            "query": query,
            "per_page": per_page,
            "returned": len(response.results),
            "first_title": first.title,
            "first_url": first.source_url,
            "credential_mode": "anonymous",
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; OpenAlex live query was not sent",
            details={"credential_mode": "anonymous"},
        )
        return

    await run_check(
        recorder,
        "openalex_registry",
        verify_openalex_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "openalex_anonymous_live_search",
        lambda: run_anonymous_openalex_search(query=args.query, per_page=args.per_page),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run one explicit anonymous OpenAlex live smoke.")
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required together with --mode live before an external request is sent.",
    )
    parser.add_argument(
        "--required",
        action="store_true",
        help="Treat a live upstream failure as FAIL instead of WARN.",
    )
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Anonymous OpenAlex search query.")
    parser.add_argument(
        "--per-page",
        type=int,
        default=1,
        help="Result count for the single search request (1..10).",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.per_page <= 10:
        parser.error("--per-page must be within 1..10")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="openalex_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
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
