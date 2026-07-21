#!/usr/bin/env python3
"""Manual DOAB OAI-PMH contract and metadata-only smoke."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from typing import Any

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check


DEFAULT_QUERY = "história"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_doab_registered() -> tuple[str, dict[str, object]]:
    """Confirm the documented experimental, explicit-only OAI-PMH source contract."""
    from souwen.registry import get

    adapter = get("doab")
    require(adapter is not None, "source 'doab' is not registered")
    require(adapter.domain == "book", f"unexpected DOAB domain: {adapter.domain!r}")
    require(adapter.capabilities == {"search", "get_detail"}, "DOAB capabilities drifted")
    require(adapter.default_for == set(), "DOAB must not join book:search defaults")
    require(adapter.auth_requirement == "none", "DOAB must remain anonymous")
    require(adapter.stability == "experimental", "DOAB must remain experimental")
    return (
        "doab registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "default_for": sorted(adapter.default_for),
            "auth_requirement": adapter.auth_requirement,
            "stability": adapter.stability,
        },
    )


async def run_doab_search_and_detail(
    *,
    query: str,
    per_page: int,
    file_limit: int,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[str, dict[str, object]]:
    """Send one bounded Books-set harvest and two same-record OAI metadata requests only."""
    if client_factory is None:
        from souwen.book.doab import DOABClient

        client_factory = DOABClient
    async with client_factory() as client:
        response = await client.search(query, per_page=per_page)
        require(response.results, "DOAB bounded harvest returned no matching metadata")
        first = response.results[0]
        detail = await client.get_by_id(first.source_record_id, file_limit=file_limit)
    require(detail.source == "doab", f"unexpected source: {detail.source!r}")
    require(
        detail.source_record_id == first.source_record_id, "detail ID does not match search result"
    )
    require(bool(detail.title), "DOAB detail has no title")
    bitstreams = [item for item in detail.resources if item.relation == "bitstream"]
    require(len(bitstreams) <= file_limit, "detail returned more bitstreams than requested")
    return (
        f"DOAB OAI search/detail returned record {detail.source_record_id}",
        {
            "query": query,
            "per_page": per_page,
            "file_limit": file_limit,
            "record_id": detail.source_record_id,
            "bitstream_count": len(bitstreams),
            "access_status": detail.access.status,
            "access_mode": "oai_metadata_and_declared_bitstream_links_only",
            "no_automatic_file_download": True,
            "metadata_license_separate_from_book_license": True,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; DOAB OAI-PMH requests were not sent",
        )
        return
    await run_check(
        recorder, "doab_registry", verify_doab_registered, required=True, timeout=args.timeout
    )
    await run_check(
        recorder,
        "doab_oai_bounded_search_and_detail",
        lambda: run_doab_search_and_detail(
            query=args.query, per_page=args.per_page, file_limit=args.file_limit
        ),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run explicit anonymous DOAB OAI-PMH smoke.")
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--per-page", type=int, default=1)
    parser.add_argument("--file-limit", type=int, default=3)
    args = parser.parse_args(argv)
    if not 1 <= args.per_page <= 25:
        parser.error("--per-page must be within 1..25")
    if not 1 <= args.file_limit <= 25:
        parser.error("--file-limit must be within 1..25")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")
    recorder = ResultRecorder(
        script="doab_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "contract": "official_oai_pmh_oai_dc_and_mets",
            "live_execution_confirmed": bool(args.execute),
            "required_live_failures": bool(args.required),
        },
    )
    try:
        await run_selected_checks(args, recorder)
    finally:
        try:
            recorder.write_reports(
                json_report=args.json_report, markdown_report=args.markdown_report
            )
        except Exception as exc:  # noqa: BLE001
            print(f"failed to write functional check reports: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    for check in recorder.checks:
        print(f"{check.outcome.value} {check.name}: {check.message}")
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
