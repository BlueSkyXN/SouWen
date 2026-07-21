from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import internet_archive_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder
from souwen.models import BookResult, ResourceLink, SearchResponse


def test_verify_internet_archive_registered_reports_anonymous_explicit_contract() -> None:
    message, details = check.verify_internet_archive_registered()

    assert message == "internet_archive registry contract passed"
    assert details == {
        "source": "internet_archive",
        "domain": "book",
        "capabilities": ["get_detail", "search"],
        "default_for": [],
        "auth_requirement": "none",
        "needs_config": False,
    }


@pytest.mark.asyncio
async def test_search_and_detail_uses_one_same_item_client_flow() -> None:
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
                source="internet_archive",
                total_results=1,
                per_page=per_page,
                results=[
                    BookResult(
                        source="internet_archive",
                        source_record_id="alice-item",
                        title="Search result",
                        source_url="https://archive.org/details/alice-item",
                    )
                ],
            )

        async def get_by_identifier(self, identifier: str, *, file_limit: int) -> BookResult:
            FakeClient.calls.append(("get_by_identifier", (identifier, file_limit)))
            return BookResult(
                source="internet_archive",
                source_record_id=identifier,
                title="Detail result",
                resources=[
                    ResourceLink(
                        url="https://archive.org/download/alice-item/text.txt",
                        relation="file",
                        file_name="text.txt",
                        source="internet_archive",
                    )
                ],
                source_url=f"https://archive.org/details/{identifier}",
            )

    message, details = await check.run_internet_archive_search_and_detail(
        query="collection:gutenberg AND title:Alice",
        per_page=1,
        file_limit=3,
        client_factory=FakeClient,
    )

    assert message == "Internet Archive search/detail returned item alice-item"
    assert details["first_url"] == "https://archive.org/details/alice-item"
    assert details["returned_resources"] == 1
    assert details["no_automatic_borrow_read_or_download"] is True
    assert details["license_access_record_specific"] is True
    assert FakeClient.calls == [
        ("search", ("collection:gutenberg AND title:Alice", 1)),
        ("get_by_identifier", ("alice-item", 3)),
    ]
    assert FakeClient.closed is True


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "internet-archive.json"
    markdown_report = tmp_path / "internet-archive.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/internet_archive_functional_check.py",
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
    assert report["script"] == "internet_archive_functional_check"
    assert report["mode"] == "offline"
    assert report["overall"] == "SKIP"
    assert report["environment"]["credential_mode"] == "anonymous"
    assert report["environment"]["access_mode"] == "catalog_metadata_and_resource_links_only"
    assert markdown_report.exists()


def test_live_mode_requires_explicit_execute_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        asyncio.run(check.main(["--mode", "live"]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("required", "expected_outcome", "expected_exit_code"),
    [(False, Outcome.WARN, 0), (True, Outcome.FAIL, 1)],
)
async def test_live_failures_are_warn_only_unless_required(
    monkeypatch: pytest.MonkeyPatch,
    required: bool,
    expected_outcome: Outcome,
    expected_exit_code: int,
) -> None:
    async def failing_live_check(**_kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(check, "verify_internet_archive_registered", lambda: ("ok", {}))
    monkeypatch.setattr(check, "run_internet_archive_search_and_detail", failing_live_check)
    recorder = ResultRecorder(script="test", mode="live")
    args = argparse.Namespace(
        mode="live",
        required=required,
        timeout=1.0,
        query="catalog",
        per_page=1,
        file_limit=1,
    )

    await check.run_selected_checks(args, recorder)

    assert recorder.checks[-1].outcome == expected_outcome
    assert recorder.checks[-1].required is required
    assert recorder.exit_code() == expected_exit_code
