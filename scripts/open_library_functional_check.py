#!/usr/bin/env python3
"""Manual anonymous Open Library search/detail functional smoke.

The script sends exactly one official work search and one bounded detail query
only when ``--mode live --execute`` is explicit.  It remains outside ordinary
pytest and never borrows, reads, or downloads an Internet Archive item.
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


DEFAULT_QUERY = "the lord of the rings"
_ANONYMOUS_REQUEST_INTERVAL_SECONDS = 1.1


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_open_library_registered() -> tuple[str, dict[str, object]]:
    """Confirm the manual smoke targets the canonical book-domain source."""
    from souwen.registry import get

    adapter = get("open_library")
    require(adapter is not None, "source 'open_library' is not registered")
    require(adapter.domain == "book", f"unexpected Open Library domain: {adapter.domain!r}")
    require(adapter.capabilities == {"search", "get_detail"}, "Open Library capabilities drifted")
    require(adapter.default_for == {"book:search"}, "Open Library book default drifted")
    require(adapter.auth_requirement == "none", "Open Library must remain anonymous")
    require(adapter.resolved_needs_config is False, "Open Library must not require configuration")
    return (
        "open_library registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "default_for": sorted(adapter.default_for),
            "auth_requirement": adapter.auth_requirement,
            "needs_config": adapter.resolved_needs_config,
        },
    )


async def run_open_library_search_and_detail(
    *,
    query: str,
    per_page: int,
    edition_limit: int,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[str, dict[str, object]]:
    """Perform one work search followed by one bounded detail request for that work."""
    use_default_client = client_factory is None
    if client_factory is None:
        from souwen.book.open_library import OpenLibraryClient

        client_factory = OpenLibraryClient

    async with client_factory() as client:
        response = await client.search(query, per_page=per_page)
        require(response.source == "open_library", f"unexpected source: {response.source!r}")
        require(response.results, "Open Library returned no results for the live smoke query")
        first = response.results[0]
        work_id = first.source_record_id
        require(isinstance(work_id, str) and work_id, "first result has no work ID")

        # Open Library's anonymous API limit is one request per second.  Fake
        # clients used by deterministic tests do not need this live delay.
        if use_default_client:
            await asyncio.sleep(_ANONYMOUS_REQUEST_INTERVAL_SECONDS)
        detail = await client.get_by_work_id(work_id, edition_limit=edition_limit)

    require(detail.source == "open_library", f"unexpected detail source: {detail.source!r}")
    require(detail.source_record_id == work_id, "detail work ID does not match search result")
    require(bool(detail.title), "Open Library detail has no title")
    require(len(detail.editions) <= edition_limit, "detail returned more editions than requested")
    return (
        f"Open Library search/detail returned work {work_id}",
        {
            "query": query,
            "per_page": per_page,
            "edition_limit": edition_limit,
            "returned": len(response.results),
            "work_id": work_id,
            "first_title": detail.title,
            "first_url": detail.source_url,
            "returned_editions": len(detail.editions),
            "access_mode": "catalog_metadata_only",
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; Open Library live requests were not sent",
            details={"access_mode": "catalog_metadata_only"},
        )
        return

    await run_check(
        recorder,
        "open_library_registry",
        verify_open_library_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "open_library_anonymous_live_search_and_detail",
        lambda: run_open_library_search_and_detail(
            query=args.query,
            per_page=args.per_page,
            edition_limit=args.edition_limit,
        ),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run explicit anonymous Open Library work search/detail smoke."
    )
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Open Library work search query.")
    parser.add_argument(
        "--per-page", type=int, default=1, help="Result count for the one search request (1..10)."
    )
    parser.add_argument(
        "--edition-limit",
        type=int,
        default=1,
        help="Bounded edition sample size for the one detail request (1..25).",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.per_page <= 10:
        parser.error("--per-page must be within 1..10")
    if not 1 <= args.edition_limit <= 25:
        parser.error("--edition-limit must be within 1..25")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="open_library_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "access_mode": "catalog_metadata_only",
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
