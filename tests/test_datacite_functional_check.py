from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import datacite_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder
from souwen.models import ResearchOutputResult, SearchResponse


def test_verify_datacite_registered_reports_research_output_default() -> None:
    message, details = check.verify_datacite_registered()

    assert message == "datacite registry contract passed"
    assert details == {
        "source": "datacite",
        "domain": "research_output",
        "capabilities": ["search"],
        "default_for": ["research_output:search"],
        "auth_requirement": "none",
    }


@pytest.mark.asyncio
async def test_search_and_detail_only_use_same_doi_metadata_flow() -> None:
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
                source="datacite",
                results=[
                    ResearchOutputResult(
                        source="datacite",
                        source_record_id="10.5281/zenodo.3723806",
                        title="Search result",
                        resource_type_general="Dataset",
                        source_url="https://doi.org/10.5281/zenodo.3723806",
                    )
                ],
            )

        async def get_by_doi(self, doi: str) -> ResearchOutputResult:
            self.calls.append(("get_by_doi", doi))
            return ResearchOutputResult(
                source="datacite",
                source_record_id=doi,
                title="Detail result",
                resource_type_general="Dataset",
                source_url=f"https://doi.org/{doi}",
            )

    message, details = await check.run_datacite_search_and_detail(
        query="climate dataset", per_page=1, client_factory=FakeClient
    )

    assert message == "DataCite search/detail returned DOI 10.5281/zenodo.3723806"
    assert details["resource_type_general"] == "Dataset"
    assert details["no_automatic_landing_fetch_or_download"] is True
    assert FakeClient.calls == [
        ("search", ("climate dataset", 1)),
        ("get_by_doi", "10.5281/zenodo.3723806"),
    ]


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "datacite.json"
    markdown_report = tmp_path / "datacite.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/datacite_functional_check.py",
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
    assert report["script"] == "datacite_functional_check"
    assert report["overall"] == "SKIP"
    assert report["environment"]["contract"] == "official_datacite_json_api_dois"
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

    monkeypatch.setattr(check, "verify_datacite_registered", lambda: ("ok", {}))
    monkeypatch.setattr(check, "run_datacite_search_and_detail", failing_live_check)
    recorder = ResultRecorder(script="test", mode="live")
    args = argparse.Namespace(
        mode="live", required=required, timeout=1.0, query="catalog", per_page=1
    )

    await check.run_selected_checks(args, recorder)

    assert recorder.checks[-1].outcome == expected_outcome
    assert recorder.checks[-1].required is required
    assert recorder.exit_code() == expected_exit_code
