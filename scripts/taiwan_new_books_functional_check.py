#!/usr/bin/env python3
"""Bounded Taiwan National Central Library new-books local-catalog smoke."""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from collections.abc import Sequence
from pathlib import Path

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover - direct script execution.
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check


# Observed in the current official data.gov.tw dataset 6730 resource metadata.
LIVE_SAMPLE_CSV_URL = (
    "https://www.ncl.edu.tw/OpenDataFile/0Q169585372033888603/90706411-13fd-4bfc-b3f1-ba83142a243c"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_taiwan_new_books_registered() -> tuple[str, dict[str, object]]:
    from souwen.registry import get

    adapter = get("taiwan_new_books")
    require(adapter is not None, "source 'taiwan_new_books' is not registered")
    require(adapter.domain == "book", f"unexpected domain: {adapter.domain!r}")
    require(
        adapter.default_for == set(), "Taiwan new-books must remain outside default book fanout"
    )
    return (
        "Taiwan new-books registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "access_mode": "local_catalog_metadata_only",
        },
    )


def run_taiwan_new_books_local_catalog_smoke() -> tuple[str, dict[str, object]]:
    from souwen.local_catalog import LocalCatalog
    from souwen.local_catalog.taiwan_new_books import (
        SOURCE,
        download_official_taiwan_new_books_csv,
        import_taiwan_new_books_input,
    )

    with tempfile.TemporaryDirectory(prefix="souwen-taiwan-new-books-") as temporary:
        temporary_path = Path(temporary)
        input_path = temporary_path / "new-books.csv"
        catalog = LocalCatalog(temporary_path / "local_catalog.sqlite3")
        receipt = download_official_taiwan_new_books_csv(LIVE_SAMPLE_CSV_URL, input_path)
        first_import = import_taiwan_new_books_input(catalog, input_path)
        second_import = import_taiwan_new_books_input(catalog, input_path)
        require(
            first_import["inserted"] > 0, "official CSV did not contain importable ISBN records"
        )
        require(
            second_import["unchanged"] == first_import["inserted"],
            "second import was not idempotent",
        )
        status = catalog.status()
        require(
            status.integrity == "ok" and status.fts5_available,
            "temporary catalog requirements failed",
        )
        require(
            status.source_counts.get(SOURCE) == first_import["inserted"], "source count drifted"
        )
        return (
            "Taiwan new-books CSV imported into a temporary local catalog",
            {
                "dataset_id": 6730,
                "resource_url": receipt.url,
                "observed_input_sha256": receipt.sha256,
                "observed_input_size_bytes": input_path.stat().st_size,
                "first_import": first_import,
                "second_import": second_import,
                "integrity": status.integrity,
                "fts5_available": status.fts5_available,
                "database_is_temporary": True,
                "metadata_only": True,
                "no_book_or_full_text_url_fetch": True,
            },
        )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; Taiwan new-books requests were not sent",
            details={"access_mode": "local_catalog_metadata_only"},
        )
        return
    await run_check(
        recorder,
        "taiwan_new_books_registry",
        verify_taiwan_new_books_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "taiwan_new_books_bounded_local_catalog_import",
        run_taiwan_new_books_local_catalog_smoke,
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Taiwan new-books local-catalog smoke.")
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    args = parser.parse_args(argv)
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")
    recorder = ResultRecorder(
        script="taiwan_new_books_functional_check",
        mode=args.mode,
        environment={
            "dataset_id": 6730,
            "access_mode": "local_catalog_metadata_only",
            "live_execution_confirmed": bool(args.execute),
            "required_live_failures": bool(args.required),
        },
    )
    try:
        await run_selected_checks(args, recorder)
    finally:
        recorder.write_reports(json_report=args.json_report, markdown_report=args.markdown_report)
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
