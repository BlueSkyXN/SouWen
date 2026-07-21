#!/usr/bin/env python3
"""Manual anonymous LOC search/detail smoke; never downloads a resource."""

from __future__ import annotations
import argparse
import asyncio
from collections.abc import Sequence

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check


def registered():
    from souwen.registry import get

    item = get("library_of_congress")
    assert (
        item
        and item.domain == "book"
        and item.default_for == set()
        and item.auth_requirement == "none"
    )
    return "LOC registry contract passed", {
        "source": item.name,
        "default_for": [],
        "access_mode": "metadata_only",
    }


async def live(query: str, per_page: int):
    from souwen.book.library_of_congress import LibraryOfCongressClient

    async with LibraryOfCongressClient() as client:
        response = await client.search(query, per_page=per_page)
        assert response.results, "LOC returned no search results"
        detail = await client.get_by_id(response.results[0].source_record_id)
    assert detail.source == "library_of_congress" and detail.source_url.startswith(
        "https://www.loc.gov/item/"
    )
    return "LOC search/detail returned one catalog record", {
        "query": query,
        "record_id": detail.source_record_id,
        "resource_count": len(detail.resources),
        "no_download": True,
        "rights_record_specific": True,
    }


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run explicit LOC catalog smoke.")
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--required", action="store_true")
    parser.add_argument("--query", default="alice")
    parser.add_argument("--per-page", type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.per_page <= 10:
        parser.error("--per-page must be within 1..10")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")
    recorder = ResultRecorder(
        script="library_of_congress_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "live_execution_confirmed": bool(args.execute),
        },
    )
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; LOC live requests were not sent",
        )
    else:
        await run_check(
            recorder,
            "library_of_congress_registry",
            registered,
            required=True,
            timeout=args.timeout,
        )
        await run_check(
            recorder,
            "library_of_congress_live_search_and_detail",
            lambda: live(args.query, args.per_page),
            required=bool(args.required),
            timeout=args.timeout,
        )
    recorder.write_reports(json_report=args.json_report, markdown_report=args.markdown_report)
    for check in recorder.checks:
        print(f"{check.outcome.value} {check.name}: {check.message}")
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
