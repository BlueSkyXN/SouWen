#!/usr/bin/env python3
"""Manual Internet Archive catalog search/detail functional smoke.

The script sends exactly one official Advanced Search request and one Metadata
API request for the returned identifier only when ``--mode live --execute`` is
explicit.  It inspects catalog metadata and resource links only: it never
borrows, reads, or downloads an item file.
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


DEFAULT_QUERY = "collection:gutenberg AND title:Alice"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_internet_archive_registered() -> tuple[str, dict[str, object]]:
    """Confirm this manual smoke targets the explicit book-domain provider."""
    from souwen.registry import get

    adapter = get("internet_archive")
    require(adapter is not None, "source 'internet_archive' is not registered")
    require(adapter.domain == "book", f"unexpected Internet Archive domain: {adapter.domain!r}")
    require(
        adapter.capabilities == {"search", "get_detail"}, "Internet Archive capabilities drifted"
    )
    require(adapter.default_for == set(), "Internet Archive must not join book:search defaults")
    require(adapter.auth_requirement == "none", "Internet Archive must remain anonymous")
    require(
        adapter.resolved_needs_config is False, "Internet Archive must not require configuration"
    )
    return (
        "internet_archive registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "default_for": sorted(adapter.default_for),
            "auth_requirement": adapter.auth_requirement,
            "needs_config": adapter.resolved_needs_config,
        },
    )


async def run_internet_archive_search_and_detail(
    *,
    query: str,
    per_page: int,
    file_limit: int,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[str, dict[str, object]]:
    """Perform one Advanced Search plus one bounded Metadata API request."""
    if client_factory is None:
        from souwen.book.internet_archive import InternetArchiveClient

        client_factory = InternetArchiveClient

    async with client_factory() as client:
        response = await client.search(query, per_page=per_page)
        require(response.source == "internet_archive", f"unexpected source: {response.source!r}")
        require(response.results, "Internet Archive returned no results for the live smoke query")
        first = response.results[0]
        identifier = first.source_record_id
        require(
            isinstance(identifier, str) and identifier,
            "first result has no Internet Archive identifier",
        )
        detail = await client.get_by_identifier(identifier, file_limit=file_limit)

    require(detail.source == "internet_archive", f"unexpected detail source: {detail.source!r}")
    require(detail.source_record_id == identifier, "detail identifier does not match search result")
    require(bool(detail.title), "Internet Archive detail has no title")
    require(len(detail.resources) <= file_limit, "detail returned more files than requested")
    return (
        f"Internet Archive search/detail returned item {identifier}",
        {
            "query": query,
            "per_page": per_page,
            "file_limit": file_limit,
            "returned": len(response.results),
            "identifier": identifier,
            "first_title": detail.title,
            "first_url": detail.source_url,
            "returned_resources": len(detail.resources),
            "access_mode": "catalog_metadata_and_resource_links_only",
            "no_automatic_borrow_read_or_download": True,
            "license_access_record_specific": True,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; Internet Archive live requests were not sent",
            details={"access_mode": "catalog_metadata_and_resource_links_only"},
        )
        return

    await run_check(
        recorder,
        "internet_archive_registry",
        verify_internet_archive_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "internet_archive_anonymous_live_search_and_detail",
        lambda: run_internet_archive_search_and_detail(
            query=args.query,
            per_page=args.per_page,
            file_limit=args.file_limit,
        ),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run explicit anonymous Internet Archive catalog search/detail smoke."
    )
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument(
        "--query", default=DEFAULT_QUERY, help="Internet Archive Advanced Search query."
    )
    parser.add_argument(
        "--per-page", type=int, default=1, help="Result count for the one search request (1..10)."
    )
    parser.add_argument(
        "--file-limit", type=int, default=3, help="Bounded file metadata count (1..50)."
    )
    args = parser.parse_args(argv)
    if not 1 <= args.per_page <= 10:
        parser.error("--per-page must be within 1..10")
    if not 1 <= args.file_limit <= 50:
        parser.error("--file-limit must be within 1..50")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="internet_archive_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "access_mode": "catalog_metadata_and_resource_links_only",
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
