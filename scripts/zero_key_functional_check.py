"""Live zero-key source functional check.

This script intentionally lives outside ordinary pytest. It exercises public
internet sources that do not require API keys, but whose real availability can
change independently from deterministic unit tests.
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


ZERO_KEY_SOURCES = ("google_patents", "wayback")
DEFAULT_GOOGLE_PATENTS_QUERY = "machine learning"
DEFAULT_WAYBACK_URL = "https://example.com/"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def resolve_sources(values: Sequence[str] | None) -> tuple[str, ...]:
    if not values:
        return ZERO_KEY_SOURCES
    selected = tuple(dict.fromkeys(values))
    unknown = sorted(set(selected) - set(ZERO_KEY_SOURCES))
    if unknown:
        raise argparse.ArgumentTypeError(
            "unknown source(s): {sources}; allowed: {allowed}".format(
                sources=", ".join(unknown),
                allowed=", ".join(ZERO_KEY_SOURCES),
            )
        )
    return selected


def verify_source_registered(source_name: str) -> tuple[str, dict[str, object]]:
    from souwen.registry import get

    adapter = get(source_name)
    require(adapter is not None, f"source {source_name!r} is not registered")
    return (
        f"{source_name} registry check passed",
        {
            "source": source_name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "stability": adapter.resolved_stability,
            "visibility": adapter.catalog_visibility,
        },
    )


async def run_google_patents_search(
    *,
    query: str,
    num_results: int,
    scraper_factory: Callable[..., Any] | None = None,
) -> tuple[str, dict[str, object]]:
    if scraper_factory is None:
        from souwen.patent.google_patents_scraper import GooglePatentsScraper

        scraper_factory = GooglePatentsScraper

    scraper = scraper_factory(min_delay=0, max_delay=0)
    try:
        response = await scraper.search(query, num_results=num_results)
    finally:
        close = getattr(scraper, "close", None)
        if close is not None:
            close_result = close()
            if hasattr(close_result, "__await__"):
                await close_result

    require(response.source == "google_patents", f"unexpected source: {response.source}")
    require(response.results, "google_patents returned no live results")
    require(response.total_results == len(response.results), "google_patents total mismatch")
    first = response.results[0]
    require(bool(first.patent_id), "first google_patents result has no patent_id")
    require(bool(first.title), "first google_patents result has no title")
    require(bool(first.source_url), "first google_patents result has no source_url")
    return (
        f"google_patents live search returned {len(response.results)} result(s)",
        {
            "query": query,
            "requested": num_results,
            "returned": len(response.results),
            "first_patent_id": first.patent_id,
            "first_title": first.title,
            "first_url": first.source_url,
        },
    )


async def run_wayback_availability(
    *,
    url: str,
    timeout: float,
    client_factory: Callable[..., Any] | None = None,
) -> tuple[str, dict[str, object]]:
    if client_factory is None:
        from souwen.web.wayback import WaybackClient

        client_factory = WaybackClient

    client = client_factory()
    try:
        availability = await client.check_availability(url, timeout=timeout)
        if not availability.available:
            cdx_response = await client.query_snapshots(
                url=url,
                filter_status=[200],
                limit=1,
                timeout=timeout,
            )
            if cdx_response.error is None and cdx_response.snapshots:
                first = cdx_response.snapshots[0]
                return (
                    "wayback availability fallback via CDX passed",
                    {
                        "url": url,
                        "snapshot_url": first.archive_url,
                        "timestamp": first.timestamp,
                        "status_code": first.status_code,
                        "source": "cdx_fallback",
                        "availability_error": availability.error,
                    },
                )
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close_result = close()
            if hasattr(close_result, "__await__"):
                await close_result

    require(availability.error is None, f"wayback availability error: {availability.error}")
    require(availability.available, f"wayback has no available snapshot for {url}")
    require(bool(availability.snapshot_url), "wayback availability has no snapshot_url")
    require(bool(availability.timestamp), "wayback availability has no timestamp")
    return (
        "wayback availability check passed",
        {
            "url": url,
            "snapshot_url": availability.snapshot_url,
            "timestamp": availability.timestamp,
            "status_code": availability.status_code,
        },
    )


async def run_wayback_cdx(
    *,
    url: str,
    limit: int,
    timeout: float,
    client_factory: Callable[..., Any] | None = None,
) -> tuple[str, dict[str, object]]:
    if client_factory is None:
        from souwen.web.wayback import WaybackClient

        client_factory = WaybackClient

    client = client_factory()
    try:
        response = await client.query_snapshots(
            url=url,
            filter_status=[200],
            limit=limit,
            timeout=timeout,
        )
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close_result = close()
            if hasattr(close_result, "__await__"):
                await close_result

    require(response.error is None, f"wayback CDX error: {response.error}")
    require(response.snapshots, f"wayback CDX returned no snapshots for {url}")
    first = response.snapshots[0]
    require(bool(first.timestamp), "first wayback CDX snapshot has no timestamp")
    require(bool(first.archive_url), "first wayback CDX snapshot has no archive_url")
    return (
        f"wayback CDX returned {len(response.snapshots)} snapshot(s)",
        {
            "url": url,
            "limit": limit,
            "returned": len(response.snapshots),
            "first_timestamp": first.timestamp,
            "first_archive_url": first.archive_url,
            "first_status_code": first.status_code,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    sources = resolve_sources(args.source)
    required = bool(args.required)

    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; zero-key live checks skipped",
            details={"selected_sources": list(sources)},
        )
        return

    for source_name in sources:
        await run_check(
            recorder,
            f"{source_name}_registry",
            lambda source_name=source_name: verify_source_registered(source_name),
            required=True,
            timeout=args.timeout,
        )

    if "google_patents" in sources:
        await run_check(
            recorder,
            "google_patents_live_search",
            lambda: run_google_patents_search(
                query=args.query,
                num_results=args.patent_results,
            ),
            required=required,
            timeout=args.timeout,
        )

    if "wayback" in sources:
        await run_check(
            recorder,
            "wayback_live_availability",
            lambda: run_wayback_availability(
                url=args.wayback_url,
                timeout=args.timeout,
            ),
            required=required,
            timeout=args.timeout,
        )
        await run_check(
            recorder,
            "wayback_live_cdx",
            lambda: run_wayback_cdx(
                url=args.wayback_url,
                limit=args.wayback_limit,
                timeout=args.timeout,
            ),
            required=required,
            timeout=args.timeout,
        )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run live zero-key source functional checks.")
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument(
        "--source",
        action="append",
        choices=ZERO_KEY_SOURCES,
        help="Zero-key source to check. Repeat to select multiple sources. Defaults to all.",
    )
    parser.add_argument(
        "--required",
        action="store_true",
        help="Treat live source failures as FAIL instead of WARN.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_GOOGLE_PATENTS_QUERY,
        help="Google Patents live search query.",
    )
    parser.add_argument(
        "--patent-results",
        type=int,
        default=1,
        help="Maximum Google Patents results to request.",
    )
    parser.add_argument(
        "--wayback-url",
        default=DEFAULT_WAYBACK_URL,
        help="URL to use for Wayback availability and CDX checks.",
    )
    parser.add_argument(
        "--wayback-limit",
        type=int,
        default=2,
        help="Maximum Wayback CDX snapshots to request.",
    )
    args = parser.parse_args(argv)
    if args.patent_results <= 0:
        parser.error("--patent-results must be greater than 0")
    if args.wayback_limit <= 0:
        parser.error("--wayback-limit must be greater than 0")

    selected_sources = resolve_sources(args.source)
    recorder = ResultRecorder(
        script="zero_key_functional_check",
        mode=args.mode,
        environment={
            "selected_sources": list(selected_sources),
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
        print(
            "{outcome} {name}: {message}".format(
                outcome=check.outcome.value,
                name=check.name,
                message=check.message,
            )
        )
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
