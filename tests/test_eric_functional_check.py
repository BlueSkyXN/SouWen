from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import eric_functional_check as check
from souwen.models import PaperResult, SearchResponse


def test_verify_eric_registered_reports_anonymous_contract() -> None:
    message, details = check.verify_eric_registered()

    assert message == "eric registry contract passed"
    assert details == {
        "source": "eric",
        "domain": "paper",
        "capabilities": ["search"],
        "needs_config": False,
    }


@pytest.mark.asyncio
async def test_eric_search_uses_client_factory_and_closes() -> None:
    class FakeClient:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            FakeClient.closed = True

        async def search(self, query: str, *, rows: int) -> SearchResponse:
            assert query == "education"
            assert rows == 1
            return SearchResponse(
                query=query,
                source="eric",
                total_results=1,
                per_page=rows,
                results=[
                    PaperResult(
                        source="eric",
                        title="ERIC result",
                        source_url="https://eric.ed.gov/?id=ED1",
                    )
                ],
            )

    message, details = await check.run_eric_search(
        query="education", rows=1, client_factory=FakeClient
    )

    assert message == "ERIC search returned 1 result(s)"
    assert details["first_url"] == "https://eric.ed.gov/?id=ED1"
    assert FakeClient.closed is True


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "eric.json"
    markdown_report = tmp_path / "eric.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/eric_functional_check.py",
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
    assert report["script"] == "eric_functional_check"
    assert report["mode"] == "offline"
    assert report["overall"] == "SKIP"
    assert markdown_report.exists()


def test_live_mode_requires_explicit_execute_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        asyncio.run(check.main(["--mode", "live"]))
