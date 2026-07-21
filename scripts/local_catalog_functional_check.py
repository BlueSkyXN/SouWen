#!/usr/bin/env python3
"""Bounded Project Gutenberg local-catalog import smoke.

The live check is deliberately opt-in.  It downloads exactly one official RDF
metadata record into a temporary directory, imports that input twice into a
temporary SQLite catalog, and queries the catalog locally.  It never fetches
or downloads any declared ebook/resource URL.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlparse

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover - direct script execution.
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _is_official_gutenberg_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in {"www.gutenberg.org", "gutenberg.org"}


def verify_gutenberg_registered() -> tuple[str, dict[str, object]]:
    """Confirm that Gutenberg remains an explicit-only local-catalog source."""
    from souwen.registry import get

    adapter = get("gutenberg")
    require(adapter is not None, "source 'gutenberg' is not registered")
    require(adapter.domain == "book", f"unexpected domain: {adapter.domain!r}")
    require(adapter.capabilities == {"search", "get_detail"}, "Gutenberg capabilities drifted")
    require(adapter.default_for == set(), "Gutenberg must remain outside default book fanout")
    require(adapter.auth_requirement == "none", "Gutenberg catalog import must remain anonymous")
    return (
        "gutenberg registry contract passed",
        {
            "source": adapter.name,
            "domain": adapter.domain,
            "capabilities": sorted(adapter.capabilities),
            "default_for": sorted(adapter.default_for),
            "auth_requirement": adapter.auth_requirement,
            "access_mode": "local_catalog_metadata_only",
        },
    )


def run_gutenberg_local_catalog_smoke() -> tuple[str, dict[str, object]]:
    """Download one official RDF record and exercise only the temporary local DB."""
    from souwen.local_catalog.gutenberg import (
        LIVE_SAMPLE_RDF_URL,
        SOURCE,
        download_official_gutenberg_catalog,
        import_gutenberg_input,
    )
    from souwen.local_catalog.store import LocalCatalog

    require(
        LIVE_SAMPLE_RDF_URL == "https://www.gutenberg.org/cache/epub/11/pg11.rdf",
        "live smoke must use only the bounded official pg11.rdf sample",
    )
    with tempfile.TemporaryDirectory(prefix="souwen-gutenberg-catalog-") as temporary:
        temporary_path = Path(temporary)
        input_path = temporary_path / "pg11.rdf"
        database_path = temporary_path / "local_catalog.sqlite3"
        receipt = download_official_gutenberg_catalog(LIVE_SAMPLE_RDF_URL, input_path)
        require(
            receipt.path == input_path and input_path.is_file(), "RDF sample download was not saved"
        )
        require(
            _is_official_gutenberg_url(receipt.url), "RDF sample redirect left official Gutenberg"
        )

        catalog = LocalCatalog(database_path)
        first_import = import_gutenberg_input(catalog, input_path)
        second_import = import_gutenberg_input(catalog, input_path)
        require(first_import["inserted"] == 1, "first RDF import did not insert exactly one record")
        require(second_import["unchanged"] == 1, "second RDF import was not idempotent")

        results = catalog.search_books(SOURCE, "Alice", limit=1)
        require(len(results) == 1, "local FTS query did not return the imported sample")
        book = catalog.get_book(SOURCE, results[0].source_record_id)
        status = catalog.status()
        require(status.integrity == "ok", "temporary local catalog integrity check failed")
        require(status.fts5_available, "temporary local catalog requires SQLite FTS5")

        return (
            f"Gutenberg local catalog imported and queried record {book.source_record_id}",
            {
                "sample_url": LIVE_SAMPLE_RDF_URL,
                "sample_id": book.source_record_id,
                "title": book.title,
                "observed_input_size_bytes": input_path.stat().st_size,
                "observed_input_sha256": receipt.sha256,
                "rights": book.access.rights,
                "declared_resource_count": len(book.resources),
                "first_import": first_import,
                "second_import": second_import,
                "fts_query": "Alice",
                "integrity": status.integrity,
                "fts5_available": status.fts5_available,
                "database_is_temporary": True,
                "no_ebook_or_declared_resource_url_fetch": True,
                "rights_do_not_imply_global_public_domain_or_redistribution": True,
            },
        )


async def run_selected_checks(args: argparse.Namespace, recorder: ResultRecorder) -> None:
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            outcome=Outcome.SKIP,
            required=False,
            message="offline mode requested; Gutenberg requests were not sent",
            details={"access_mode": "local_catalog_metadata_only"},
        )
        return

    await run_check(
        recorder,
        "gutenberg_registry",
        verify_gutenberg_registered,
        required=True,
        timeout=args.timeout,
    )
    await run_check(
        recorder,
        "gutenberg_bounded_local_catalog_import",
        run_gutenberg_local_catalog_smoke,
        required=bool(args.required),
        timeout=args.timeout,
    )


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the explicit bounded Project Gutenberg local-catalog smoke."
    )
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true", help="Required with --mode live.")
    parser.add_argument("--required", action="store_true", help="Fail on live upstream failure.")
    args = parser.parse_args(argv)
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")

    recorder = ResultRecorder(
        script="local_catalog_functional_check",
        mode=args.mode,
        environment={
            "credential_mode": "anonymous",
            "contract": "official_project_gutenberg_rdf_xml_local_catalog",
            "live_sample": "https://www.gutenberg.org/cache/epub/11/pg11.rdf",
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
        except Exception as exc:  # noqa: BLE001 - report write errors have a fixed exit code.
            print(f"failed to write functional check reports: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc

    for check in recorder.checks:
        print(f"{check.outcome.value} {check.name}: {check.message}")
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
