#!/usr/bin/env python3
"""Manual OpenCitations V2 count/citations/references functional smoke."""

from __future__ import annotations

import argparse
import asyncio

try:
    from scripts._functional_common import Outcome, ResultRecorder, add_common_args, run_check
except ModuleNotFoundError:  # pragma: no cover - direct script execution.
    from _functional_common import Outcome, ResultRecorder, add_common_args, run_check

DEFAULT_IDENTIFIER = "doi:10.1038/nphys1170"


def verify_registered() -> dict[str, object]:
    from souwen.registry import get

    adapter = get("opencitations")
    assert adapter is not None and adapter.resolved_needs_config is False
    assert {
        "opencitations:citation_count",
        "opencitations:citations",
        "opencitations:references",
    } <= adapter.capabilities
    return {"source": adapter.name, "capabilities": sorted(adapter.capabilities)}


async def live(identifier: str) -> dict[str, object]:
    from souwen.citations import get_citation_count, get_incoming_citations, get_references

    count, incoming, references = await asyncio.gather(
        get_citation_count(identifier),
        get_incoming_citations(identifier, max_edges=10),
        get_references(identifier, max_edges=10),
    )
    assert count.source == incoming.source == references.source == "opencitations"
    return {
        "identifier": count.identifier.canonical,
        "count": count.count,
        "incoming": incoming.returned_edges,
        "references": references.returned_edges,
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, default_mode="offline", modes=("offline", "live"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--required", action="store_true")
    parser.add_argument("--identifier", default=DEFAULT_IDENTIFIER)
    args = parser.parse_args(argv)
    if args.mode == "live" and not args.execute:
        parser.error("--mode live requires --execute")
    recorder = ResultRecorder(script="opencitations_functional_check", mode=args.mode)
    if args.mode == "offline":
        recorder.record(
            "offline_mode",
            Outcome.SKIP,
            required=False,
            message="offline mode requested; no requests sent",
        )
    else:
        await run_check(
            recorder,
            "opencitations_registry",
            verify_registered,
            required=True,
            timeout=args.timeout,
        )
        await run_check(
            recorder,
            "opencitations_live",
            lambda: live(args.identifier),
            required=bool(args.required),
            timeout=args.timeout,
        )
    recorder.write_reports(json_report=args.json_report, markdown_report=args.markdown_report)
    for check in recorder.checks:
        print(f"{check.outcome.value} {check.name}: {check.message}")
    return recorder.exit_code()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
