from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import osti_functional_check as check
from souwen.models import PaperResult, SearchResponse


def test_verify_osti_registered_reports_anonymous_contract() -> None:
    message, details = check.verify_osti_registered()

    assert message == "OSTI registry contract passed"
    assert details == {
        "source": "osti",
        "domain": "paper",
        "capabilities": ["get_detail", "search"],
        "needs_config": False,
    }


@pytest.mark.asyncio
async def test_osti_search_and_detail_uses_client_factory_and_closes() -> None:
    class FakeClient:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            FakeClient.closed = True

        async def search(self, query: str, *, rows: int) -> SearchResponse:
            assert query == "machine learning"
            assert rows == 1
            return SearchResponse(
                query=query,
                source="osti",
                total_results=1,
                per_page=rows,
                results=[
                    PaperResult(
                        source="osti",
                        title="OSTI result",
                        source_url="https://www.osti.gov/biblio/3012392",
                        raw={"osti_id": "3012392"},
                    )
                ],
            )

        async def get_by_id(self, osti_id: str) -> PaperResult:
            assert osti_id == "3012392"
            return PaperResult(
                source="osti",
                title="OSTI detail",
                source_url="https://www.osti.gov/biblio/3012392",
                raw={"osti_id": osti_id},
            )

    message, details = await check.run_osti_search_and_detail(
        query="machine learning", rows=1, client_factory=FakeClient
    )

    assert message == "OSTI search/detail returned record 3012392"
    assert details["first_url"] == "https://www.osti.gov/biblio/3012392"
    assert FakeClient.closed is True


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "osti.json"
    markdown_report = tmp_path / "osti.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/osti_functional_check.py",
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
    assert report["script"] == "osti_functional_check"
    assert report["mode"] == "offline"
    assert report["overall"] == "SKIP"
    assert markdown_report.exists()


def test_live_mode_requires_explicit_execute_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        asyncio.run(check.main(["--mode", "live"]))
