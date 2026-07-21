from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import figshare_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder
from souwen.models import ResearchOutputResult, ResourceAccess, ResourceLink, SearchResponse


def test_verify_figshare_registered_reports_explicit_anonymous_contract() -> None:
    message, details = check.verify_figshare_registered()

    assert message == "figshare registry contract passed"
    assert details == {
        "source": "figshare",
        "domain": "research_output",
        "capabilities": ["get_detail", "search"],
        "default_for": [],
        "auth_requirement": "none",
    }


@pytest.mark.asyncio
async def test_search_and_detail_only_use_same_article_metadata_flow() -> None:
    class FakeClient:
        calls: list[tuple[str, object]] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def search(self, query: str, *, page_size: int) -> SearchResponse:
            self.calls.append(("search", (query, page_size)))
            return SearchResponse(
                query=query,
                source="figshare",
                results=[
                    ResearchOutputResult(
                        source="figshare",
                        source_record_id="33046703",
                        title="Search result",
                        resource_type_general="Dataset",
                        resource_type="dataset",
                        source_url="https://figshare.com/articles/dataset/33046703",
                    )
                ],
            )

        async def get_by_id(self, article_id: str) -> ResearchOutputResult:
            self.calls.append(("get_by_id", article_id))
            return ResearchOutputResult(
                source="figshare",
                source_record_id=article_id,
                title="Detail result",
                resource_type_general="Dataset",
                resource_type="dataset",
                resources=[
                    ResourceLink(
                        url="https://ndownloader.figshare.com/files/1",
                        relation="declared_file_url",
                        source="figshare",
                        is_link_only=True,
                        access=ResourceAccess(status="metadata_only"),
                    )
                ],
                source_url="https://figshare.com/articles/dataset/33046703",
            )

    message, details = await check.run_figshare_search_and_detail(
        query="climate dataset", page_size=1, client_factory=FakeClient
    )

    assert message == "Figshare search/detail returned article 33046703"
    assert details["declared_file_count"] == 1
    assert details["link_only_file_count"] == 1
    assert details["no_automatic_file_fetch_or_download"] is True
    assert FakeClient.calls == [
        ("search", ("climate dataset", 1)),
        ("get_by_id", "33046703"),
    ]


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "figshare.json"
    markdown_report = tmp_path / "figshare.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/figshare_functional_check.py",
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
    assert report["script"] == "figshare_functional_check"
    assert report["overall"] == "SKIP"
    assert report["environment"]["contract"] == "official_figshare_public_api_v2_articles"
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

    monkeypatch.setattr(check, "verify_figshare_registered", lambda: ("ok", {}))
    monkeypatch.setattr(check, "run_figshare_search_and_detail", failing_live_check)
    recorder = ResultRecorder(script="test", mode="live")
    args = argparse.Namespace(
        mode="live", required=required, timeout=1.0, query="catalog", page_size=1
    )

    await check.run_selected_checks(args, recorder)

    assert recorder.checks[-1].outcome == expected_outcome
    assert recorder.checks[-1].required is required
    assert recorder.exit_code() == expected_exit_code
