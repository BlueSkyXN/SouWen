#!/usr/bin/env python3
"""Manual bounded Wikisource search/detail functional smoke.

The script sends at most one official Chinese Wikisource search and one
metadata/content request for one returned page when ``--mode live --execute``
is explicit.  It never imports dumps, recursively fetches subpages, or writes
back to Wikimedia.
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


DEFAULT_QUERY = "論語"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_wikisource_registered() -> tuple[str, dict[str, object]]:
    """Confirm the smoke targets the fixed anonymous book-domain provider."""
    from souwen.registry import get

    adapter = get("wikisource")
    require(adapter is not None, "source 'wikisource' is not registered")
    require(adapter.domain == "book", f"unexpected Wikisource domain: {adapter.domain!r}")
    require(adapter.capabilities == {"search", "get_detail"}, "Wikisource capabilities drifted")
    require(adapter.default_for == set(), "Wikisource must not join book:search defaults")
    require(adapter.auth_requirement == "none", "Wikisource must remain anonymous")
    require(adapter.resolved_needs_config is False, "Wikisource must not require configuration")
    return (
        "wikisource registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "default_for": sorted(adapter.default_for),
            "auth_requirement": adapter.auth_requirement,
            "needs_config": adapter.resolved_needs_config,
            "language_allowlist": ["zh", "en"],
        },
    )


async def run_wikisource_search_and_detail(
    *,
    query: str,
    per_page: int,
    max_content_chars: int,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[str, dict[str, object]]:
    """Perform one Chinese search and one bounded detail request for its first page."""
    if client_factory is None:
        from souwen.book.wikisource import WikisourceClient

        client_factory = WikisourceClient

    async with client_factory() as client:
        response = await client.search(query, per_page=per_page, language="zh")
        require(response.source == "wikisource", f"unexpected source: {response.source!r}")
        require(response.results, "Wikisource returned no results for the live smoke query")
        first = response.results[0]
        title = first.title
        require(isinstance(title, str) and title, "first result has no Wikisource title")
        detail = await client.get_page_detail(
            title,
            language="zh",
            content_format="text",
            max_content_chars=max_content_chars,
            include_subpages=False,
        )

    require(detail.source == "wikisource", f"unexpected detail source: {detail.source!r}")
    require(detail.language == "zh", f"unexpected detail language: {detail.language!r}")
    require(bool(detail.title), "Wikisource detail has no title")
    require(
        len(detail.revision.content) <= max_content_chars,
        "detail returned more content than the configured bound",
    )
    require(detail.subpages == [], "live smoke must not fetch or return subpages")
    return (
        f"Wikisource search/detail returned page {detail.title}",
        {
            "query": query,
            "language": "zh",
            "per_page": per_page,
            "max_content_chars": max_content_chars,
            "returned": len(response.results),
            "title": detail.title,
            "page_id": detail.page_id,
            "revision_id": detail.revision.revision_id,
            "source_url": detail.source_url,
            "content_truncated": detail.revision.content_truncated,
            "returned_subpages": len(detail.subpages),
            "access_mode": "one_bounded_page_and_revision_only",
            "no_dump_recursive_fetch_or_write": True,
            "rights_record_and_jurisdiction_specific": True,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; Wikisource live requests were not sent",
            details={"access_mode": "one_bounded_page_and_revision_only"},
        )
        return

    await run_check(
        recorder,
        "wikisource_registry",
        verify_wikisource_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "wikisource_anonymous_live_zh_search_and_detail",
        lambda: run_wikisource_search_and_detail(
            query=args.query,
            per_page=args.per_page,
            max_content_chars=args.max_content_chars,
        ),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run explicit anonymous Chinese Wikisource search/detail smoke."
    )
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Chinese Wikisource search query.")
    parser.add_argument(
        "--per-page", type=int, default=1, help="Result count for the one search request (1..5)."
    )
    parser.add_argument(
        "--max-content-chars",
        type=int,
        default=2_000,
        help="Maximum returned revision characters for the one detail request (1..100000).",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.per_page <= 5:
        parser.error("--per-page must be within 1..5")
    if not 1 <= args.max_content_chars <= 100_000:
        parser.error("--max-content-chars must be within 1..100000")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="wikisource_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "language": "zh",
            "access_mode": "one_bounded_page_and_revision_only",
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
