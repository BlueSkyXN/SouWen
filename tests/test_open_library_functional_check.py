from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import open_library_functional_check as check
from souwen.models import BookEdition, BookResult, SearchResponse


def test_verify_open_library_registered_reports_anonymous_book_contract() -> None:
    message, details = check.verify_open_library_registered()

    assert message == "open_library registry contract passed"
    assert details == {
        "source": "open_library",
        "domain": "book",
        "capabilities": ["get_detail", "search"],
        "default_for": ["book:search"],
        "auth_requirement": "none",
        "needs_config": False,
    }


@pytest.mark.asyncio
async def test_open_library_search_and_detail_uses_one_bounded_work_client() -> None:
    class FakeClient:
        closed = False
        calls: list[tuple[str, object]] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            FakeClient.closed = True

        async def search(self, query: str, *, per_page: int) -> SearchResponse:
            FakeClient.calls.append(("search", (query, per_page)))
            return SearchResponse(
                query=query,
                source="open_library",
                total_results=1,
                per_page=per_page,
                results=[
                    BookResult(
                        source="open_library",
                        source_record_id="OL123W",
                        title="Search result",
                        source_url="https://openlibrary.org/works/OL123W",
                    )
                ],
            )

        async def get_by_work_id(self, work_id: str, *, edition_limit: int) -> BookResult:
            FakeClient.calls.append(("get_by_work_id", (work_id, edition_limit)))
            return BookResult(
                source="open_library",
                source_record_id=work_id,
                title="Detail result",
                editions=[BookEdition(olid="OL456M")],
                source_url=f"https://openlibrary.org/works/{work_id}",
            )

    message, details = await check.run_open_library_search_and_detail(
        query="the lord of the rings",
        per_page=1,
        edition_limit=1,
        client_factory=FakeClient,
    )

    assert message == "Open Library search/detail returned work OL123W"
    assert details["first_url"] == "https://openlibrary.org/works/OL123W"
    assert details["returned_editions"] == 1
    assert FakeClient.calls == [
        ("search", ("the lord of the rings", 1)),
        ("get_by_work_id", ("OL123W", 1)),
    ]
    assert FakeClient.closed is True


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "open-library.json"
    markdown_report = tmp_path / "open-library.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/open_library_functional_check.py",
            "--mode",
            "offline",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "SKIP offline_mode" in completed.stdout
    report = json.loads(json_report.read_text(encoding="utf-8"))
    assert report["script"] == "open_library_functional_check"
    assert report["mode"] == "offline"
    assert report["overall"] == "SKIP"
    assert report["environment"]["credential_mode"] == "anonymous"
    assert report["environment"]["access_mode"] == "catalog_metadata_only"
    assert markdown_report.exists()


def test_live_mode_requires_explicit_execute_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        asyncio.run(check.main(["--mode", "live"]))
