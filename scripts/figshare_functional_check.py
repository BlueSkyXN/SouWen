#!/usr/bin/env python3
"""Manual anonymous Figshare public article search/detail smoke."""

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


DEFAULT_QUERY = "climate dataset"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_figshare_registered() -> tuple[str, dict[str, object]]:
    """Confirm the explicit anonymous Figshare registry contract."""
    from souwen.registry import get

    adapter = get("figshare")
    require(adapter is not None, "source 'figshare' is not registered")
    require(adapter.domain == "research_output", f"unexpected domain: {adapter.domain!r}")
    require(adapter.capabilities == {"search", "get_detail"}, "Figshare capabilities drifted")
    require(adapter.default_for == set(), "Figshare must remain explicit-only")
    require(adapter.auth_requirement == "none", "Figshare must remain anonymous")
    return (
        "figshare registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "default_for": sorted(adapter.default_for),
            "auth_requirement": adapter.auth_requirement,
        },
    )


async def run_figshare_search_and_detail(
    *, query: str, page_size: int, client_factory: Callable[[], Any] | None = None
) -> tuple[str, dict[str, object]]:
    """Perform one public search and one detail request for the same article only."""
    if client_factory is None:
        from souwen.research_output.figshare import FigshareClient

        client_factory = FigshareClient
    async with client_factory() as client:
        response = await client.search(query, page_size=page_size)
        require(response.results, "Figshare returned no records for the live smoke query")
        first = response.results[0]
        detail = await client.get_by_id(first.source_record_id)
    require(detail.source == "figshare", f"unexpected source: {detail.source!r}")
    require(
        detail.source_record_id == first.source_record_id, "detail article ID does not match search"
    )
    require(bool(detail.title), "Figshare detail has no title")
    require(bool(detail.resource_type), "Figshare detail has no defined type")
    return (
        f"Figshare search/detail returned article {detail.source_record_id}",
        {
            "query": query,
            "page_size": page_size,
            "article_id": detail.source_record_id,
            "resource_type_general": detail.resource_type_general,
            "resource_type": detail.resource_type,
            "rights_count": len(detail.rights_list),
            "declared_file_count": len(
                [
                    resource
                    for resource in detail.resources
                    if resource.relation == "declared_file_url"
                ]
            ),
            "link_only_file_count": len(
                [resource for resource in detail.resources if resource.is_link_only is True]
            ),
            "no_automatic_file_fetch_or_download": True,
            "rights_do_not_imply_download_authorization": True,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; Figshare requests were not sent",
        )
        return
    await run_check(
        recorder,
        "figshare_registry",
        verify_figshare_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "figshare_public_search_and_detail",
        lambda: run_figshare_search_and_detail(query=args.query, page_size=args.page_size),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run explicit anonymous Figshare public article smoke."
    )
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--page-size", type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.page_size <= 100:
        parser.error("--page-size must be within 1..100")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")
    recorder = ResultRecorder(
        script="figshare_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "contract": "official_figshare_public_api_v2_articles",
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
