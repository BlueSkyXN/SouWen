from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import doab_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder
from souwen.models import BookResult, ResourceAccess, ResourceLink, SearchResponse


def test_verify_doab_registered_reports_explicit_experimental_contract() -> None:
    message, details = check.verify_doab_registered()

    assert message == "doab registry contract passed"
    assert details == {
        "source": "doab",
        "domain": "book",
        "capabilities": ["get_detail", "search"],
        "default_for": [],
        "auth_requirement": "none",
        "stability": "experimental",
    }


@pytest.mark.asyncio
async def test_search_and_detail_only_use_same_record_metadata_flow() -> None:
    class FakeClient:
        calls: list[tuple[str, object]] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def search(self, query: str, *, per_page: int) -> SearchResponse:
            self.calls.append(("search", (query, per_page)))
            return SearchResponse(
                query=query,
                source="doab",
                results=[
                    BookResult(
                        source="doab",
                        source_record_id="20.500.12854/1234",
                        title="Search result",
                        source_url="https://directory.doabooks.org/handle/20.500.12854/1234",
                    )
                ],
            )

        async def get_by_id(self, record_id: str, *, file_limit: int) -> BookResult:
            self.calls.append(("get_by_id", (record_id, file_limit)))
            access = ResourceAccess(status="open_access")
            resource = ResourceLink(
                url="https://directory.doabooks.org/bitstream/20.500.12854/1234/1/book.pdf",
                relation="bitstream",
                source="doab",
                access=access,
            )
            return BookResult(
                source="doab",
                source_record_id=record_id,
                title="Detail result",
                resources=[resource],
                access=access,
                source_url="https://directory.doabooks.org/handle/20.500.12854/1234",
            )

    message, details = await check.run_doab_search_and_detail(
        query="climate", per_page=1, file_limit=3, client_factory=FakeClient
    )

    assert message == "DOAB OAI search/detail returned record 20.500.12854/1234"
    assert details["bitstream_count"] == 1
    assert details["no_automatic_file_download"] is True
    assert details["metadata_license_separate_from_book_license"] is True
    assert FakeClient.calls == [
        ("search", ("climate", 1)),
        ("get_by_id", ("20.500.12854/1234", 3)),
    ]


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "doab.json"
    markdown_report = tmp_path / "doab.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/doab_functional_check.py",
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
    assert report["script"] == "doab_functional_check"
    assert report["mode"] == "offline"
    assert report["overall"] == "SKIP"
    assert report["environment"]["contract"] == "official_oai_pmh_oai_dc_and_mets"
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

    monkeypatch.setattr(check, "verify_doab_registered", lambda: ("ok", {}))
    monkeypatch.setattr(check, "run_doab_search_and_detail", failing_live_check)
    recorder = ResultRecorder(script="test", mode="live")
    args = argparse.Namespace(
        mode="live", required=required, timeout=1.0, query="catalog", per_page=1, file_limit=1
    )

    await check.run_selected_checks(args, recorder)

    assert recorder.checks[-1].outcome == expected_outcome
    assert recorder.checks[-1].required is required
    assert recorder.exit_code() == expected_exit_code
