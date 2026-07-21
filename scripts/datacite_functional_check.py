#!/usr/bin/env python3
"""Manual anonymous DataCite metadata search/detail smoke."""

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


def verify_datacite_registered() -> tuple[str, dict[str, object]]:
    """Confirm the core anonymous research-output default contract."""
    from souwen.registry import get

    adapter = get("datacite")
    require(adapter is not None, "source 'datacite' is not registered")
    require(adapter.domain == "research_output", f"unexpected domain: {adapter.domain!r}")
    require(adapter.capabilities == {"search"}, "DataCite capabilities drifted")
    require(adapter.default_for == {"research_output:search"}, "DataCite default drifted")
    require(adapter.auth_requirement == "none", "DataCite must remain anonymous")
    return (
        "datacite registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "default_for": sorted(adapter.default_for),
            "auth_requirement": adapter.auth_requirement,
        },
    )


async def run_datacite_search_and_detail(
    *, query: str, per_page: int, client_factory: Callable[[], Any] | None = None
) -> tuple[str, dict[str, object]]:
    """Perform one anonymous list request and one same-record metadata detail request only."""
    if client_factory is None:
        from souwen.research_output.datacite import DataCiteClient

        client_factory = DataCiteClient
    async with client_factory() as client:
        response = await client.search(query, per_page=per_page)
        require(response.results, "DataCite returned no records for the live smoke query")
        first = response.results[0]
        detail = await client.get_by_doi(first.source_record_id)
    require(detail.source == "datacite", f"unexpected source: {detail.source!r}")
    require(detail.source_record_id == first.source_record_id, "detail DOI does not match search")
    require(bool(detail.title), "DataCite detail has no title")
    require(bool(detail.resource_type_general), "DataCite detail has no resourceTypeGeneral")
    return (
        f"DataCite search/detail returned DOI {detail.source_record_id}",
        {
            "query": query,
            "per_page": per_page,
            "doi": detail.source_record_id,
            "resource_type_general": detail.resource_type_general,
            "resource_type": detail.resource_type,
            "rights_count": len(detail.rights_list),
            "content_url_count": len(detail.content_urls),
            "resource_link_count": len(detail.resources),
            "access_mode": "metadata_landing_and_declared_content_urls_only",
            "no_automatic_landing_fetch_or_download": True,
            "rights_do_not_imply_download_authorization": True,
        },
    )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; DataCite requests were not sent",
        )
        return
    await run_check(
        recorder,
        "datacite_registry",
        verify_datacite_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "datacite_anonymous_search_and_detail",
        lambda: run_datacite_search_and_detail(query=args.query, per_page=args.per_page),
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run explicit anonymous DataCite metadata smoke.")
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--per-page", type=int, default=1)
    args = parser.parse_args(argv)
    if not 1 <= args.per_page <= 100:
        parser.error("--per-page must be within 1..100")
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")
    recorder = ResultRecorder(
        script="datacite_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "contract": "official_datacite_json_api_dois",
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
