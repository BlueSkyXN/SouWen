from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import zero_key_functional_check as check
from souwen.models import (
    PatentResult,
    SearchResponse,
    WaybackAvailability,
    WaybackCDXResponse,
    WaybackSnapshot,
)


def test_resolve_sources_defaults_and_deduplicates() -> None:
    assert check.resolve_sources(None) == ("google_patents", "wayback")
    assert check.resolve_sources(["wayback", "wayback", "google_patents"]) == (
        "wayback",
        "google_patents",
    )


def test_verify_source_registered_reports_catalog_metadata() -> None:
    message, details = check.verify_source_registered("wayback")

    assert message == "wayback registry check passed"
    assert details["source"] == "wayback"
    assert details["domain"] == "archive"
    assert "fetch" in details["capabilities"]


@pytest.mark.asyncio
async def test_google_patents_check_uses_scraper_factory_and_closes() -> None:
    class FakeScraper:
        closed = False

        def __init__(self, *, min_delay: float, max_delay: float) -> None:
            assert min_delay == 0
            assert max_delay == 0

        async def search(self, query: str, num_results: int) -> SearchResponse:
            assert query == "battery"
            assert num_results == 1
            return SearchResponse(
                query=query,
                source="google_patents",
                total_results=1,
                results=[
                    PatentResult(
                        source="google_patents",
                        title="Battery patent",
                        patent_id="US1234567A",
                        source_url="https://patents.google.com/patent/US1234567A",
                    )
                ],
            )

        async def close(self) -> None:
            FakeScraper.closed = True

    message, details = await check.run_google_patents_search(
        query="battery",
        num_results=1,
        scraper_factory=FakeScraper,
    )

    assert message == "google_patents live search returned 1 result(s)"
    assert details["first_patent_id"] == "US1234567A"
    assert FakeScraper.closed is True


@pytest.mark.asyncio
async def test_wayback_checks_use_client_factory_and_close() -> None:
    class FakeClient:
        close_count = 0

        async def check_availability(self, url: str, timeout: float) -> WaybackAvailability:
            assert url == "https://example.com/"
            assert timeout == 3
            return WaybackAvailability(
                url=url,
                available=True,
                snapshot_url="https://web.archive.org/web/20240101000000/https://example.com/",
                timestamp="20240101000000",
                status_code=200,
            )

        async def query_snapshots(
            self,
            *,
            url: str,
            filter_status: list[int],
            limit: int,
            timeout: float,
        ) -> WaybackCDXResponse:
            assert url == "https://example.com/"
            assert filter_status == [200]
            assert limit == 1
            assert timeout == 3
            return WaybackCDXResponse(
                url=url,
                snapshots=[
                    WaybackSnapshot(
                        timestamp="20240101000000",
                        url=url,
                        archive_url="https://web.archive.org/web/20240101000000/https://example.com/",
                        status_code=200,
                    )
                ],
                total=1,
            )

        async def close(self) -> None:
            FakeClient.close_count += 1

    availability_message, availability_details = await check.run_wayback_availability(
        url="https://example.com/",
        timeout=3,
        client_factory=FakeClient,
    )
    cdx_message, cdx_details = await check.run_wayback_cdx(
        url="https://example.com/",
        limit=1,
        timeout=3,
        client_factory=FakeClient,
    )

    assert availability_message == "wayback availability check passed"
    assert availability_details["timestamp"] == "20240101000000"
    assert cdx_message == "wayback CDX returned 1 snapshot(s)"
    assert cdx_details["first_status_code"] == 200
    assert FakeClient.close_count == 2


@pytest.mark.asyncio
async def test_wayback_availability_falls_back_to_cdx_snapshot() -> None:
    class FakeClient:
        closed = False

        async def check_availability(self, url: str, timeout: float) -> WaybackAvailability:
            assert url == "https://example.com/"
            assert timeout == 3
            return WaybackAvailability(url=url, available=False)

        async def query_snapshots(
            self,
            *,
            url: str,
            filter_status: list[int],
            limit: int,
            timeout: float,
        ) -> WaybackCDXResponse:
            assert url == "https://example.com/"
            assert filter_status == [200]
            assert limit == 1
            assert timeout == 3
            return WaybackCDXResponse(
                url=url,
                snapshots=[
                    WaybackSnapshot(
                        timestamp="20240101000000",
                        url=url,
                        archive_url="https://web.archive.org/web/20240101000000/https://example.com/",
                        status_code=200,
                    )
                ],
                total=1,
            )

        async def close(self) -> None:
            FakeClient.closed = True

    message, details = await check.run_wayback_availability(
        url="https://example.com/",
        timeout=3,
        client_factory=FakeClient,
    )

    assert message == "wayback availability fallback via CDX passed"
    assert details["source"] == "cdx_fallback"
    assert details["timestamp"] == "20240101000000"
    assert FakeClient.closed is True


def test_offline_mode_writes_skip_report(tmp_path: Path) -> None:
    json_report = tmp_path / "zero-key.json"
    markdown_report = tmp_path / "zero-key.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/zero_key_functional_check.py",
            "--mode",
            "offline",
            "--source",
            "wayback",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "SKIP offline_mode" in completed.stdout
    data = json.loads(json_report.read_text(encoding="utf-8"))
    assert data["script"] == "zero_key_functional_check"
    assert data["mode"] == "offline"
    assert data["overall"] == "SKIP"
    assert data["environment"]["selected_sources"] == ["wayback"]
    assert data["checks"][0]["name"] == "offline_mode"
    assert data["checks"][0]["outcome"] == "SKIP"
    assert "Overall: **SKIP**" in markdown_report.read_text(encoding="utf-8")
