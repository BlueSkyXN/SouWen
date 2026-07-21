#!/usr/bin/env python3
"""Manual LibriVox catalog/detail smoke; never fetches audio or RSS media."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from typing import Any

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover - direct ``python scripts/...`` execution.
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check


DEFAULT_QUERY = "pride and prejudice"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_librivox_registered() -> tuple[str, dict[str, object]]:
    """Confirm the anonymous, explicit-only book catalog contract."""
    from souwen.registry import get

    adapter = get("librivox")
    require(adapter is not None, "source 'librivox' is not registered")
    require(adapter.domain == "book", f"unexpected LibriVox domain: {adapter.domain!r}")
    require(adapter.capabilities == {"search", "get_detail"}, "LibriVox capabilities drifted")
    require(adapter.default_for == set(), "LibriVox must not join book:search defaults")
    require(adapter.auth_requirement == "none", "LibriVox must remain anonymous")
    require(adapter.resolved_needs_config is False, "LibriVox must not require configuration")
    return (
        "librivox registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "default_for": sorted(adapter.default_for),
            "auth_requirement": adapter.auth_requirement,
            "needs_config": adapter.resolved_needs_config,
        },
    )


async def run_librivox_search_and_detail(
    *,
    query: str,
    per_page: int,
    audio_limit: int,
    search_field: str = "title",
    client_factory: Callable[[], Any] | None = None,
) -> tuple[str, dict[str, object]]:
    """Make one catalog search and one same-record detail metadata request only."""
    if client_factory is None:
        from souwen.book.librivox import LibriVoxClient

        client_factory = LibriVoxClient

    async with client_factory() as client:
        response = await client.search(query, per_page=per_page, search_field=search_field)
        require(response.source == "librivox", f"unexpected source: {response.source!r}")
        require(response.results, "LibriVox returned no results for the live smoke query")
        first = response.results[0]
        audiobook_id = first.source_record_id
        require(
            isinstance(audiobook_id, str) and audiobook_id.isdigit(),
            "first result has no numeric LibriVox audiobook ID",
        )
        detail = await client.get_by_id(audiobook_id, audio_limit=audio_limit)

    require(detail.source == "librivox", f"unexpected detail source: {detail.source!r}")
    require(detail.source_record_id == audiobook_id, "detail ID does not match search result")
    require(bool(detail.title), "LibriVox detail has no title")
    require(detail.access.status == "unknown", "LibriVox must not infer public-domain status")
    require(
        len(detail.audio_sections) <= audio_limit, "detail returned more sections than requested"
    )
    audio_resources = [resource for resource in detail.resources if resource.relation == "audio"]
    require(
        len(audio_resources) <= audio_limit,
        "detail returned more audio links than requested",
    )
    return (
        f"LibriVox search/detail returned audiobook {audiobook_id}",
        {
            "query": query,
            "search_field": search_field,
            "per_page": per_page,
            "audio_limit": audio_limit,
            "returned": len(response.results),
            "audiobook_id": audiobook_id,
            "first_title": detail.title,
            "first_url": detail.source_url,
            "audio_section_count": len(detail.audio_sections),
            "audio_resource_count": len(audio_resources),
            "reader_count": len(detail.readers),
            "access_mode": "catalog_metadata_and_declared_audio_rss_links_only",
            "no_automatic_audio_or_rss_download": True,
            "rights_law_and_jurisdiction_specific": True,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; LibriVox live requests were not sent",
            details={"access_mode": "catalog_metadata_and_declared_audio_rss_links_only"},
        )
        return

    await run_check(
        recorder,
        "librivox_registry",
        verify_librivox_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "librivox_anonymous_live_search_and_detail",
        lambda: run_librivox_search_and_detail(
            query=args.query,
            per_page=args.per_page,
            audio_limit=args.audio_limit,
            search_field=args.search_field,
        ),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run explicit anonymous LibriVox catalog/detail smoke."
    )
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="LibriVox title search query.")
    parser.add_argument(
        "--search-field",
        choices=("title", "author"),
        default="title",
        help="Official LibriVox search field for the one catalog request.",
    )
    parser.add_argument(
        "--per-page", type=int, default=1, help="Result count for the one search request (1..10)."
    )
    parser.add_argument(
        "--audio-limit", type=int, default=3, help="Bounded section/audio metadata count (1..50)."
    )
    args = parser.parse_args(argv)
    if not 1 <= args.per_page <= 10:
        parser.error("--per-page must be within 1..10")
    if not 1 <= args.audio_limit <= 50:
        parser.error("--audio-limit must be within 1..50")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="librivox_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "access_mode": "catalog_metadata_and_declared_audio_rss_links_only",
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
        except Exception as exc:  # noqa: BLE001 - report write failures use a fixed exit code.
            print(f"failed to write functional check reports: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc

    for check in recorder.checks:
        print(f"{check.outcome.value} {check.name}: {check.message}")
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
