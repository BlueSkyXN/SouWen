from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import openalex_functional_check as check
from souwen.models import PaperResult, SearchResponse


def test_verify_openalex_registered_reports_optional_key_contract() -> None:
    message, details = check.verify_openalex_registered()

    assert message == "openalex registry contract passed"
    assert details == {
        "source": "openalex",
        "domain": "paper",
        "capabilities": ["search"],
        "config_field": "openalex_api_key",
        "needs_config": False,
    }


@pytest.mark.asyncio
async def test_anonymous_search_clears_configured_key_and_closes_client() -> None:
    class FakeClient:
        closed = False

        def __init__(self) -> None:
            self.api_key = "must-not-be-sent"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            FakeClient.closed = True

        async def search(self, query: str, *, per_page: int) -> SearchResponse:
            assert self.api_key is None
            assert query == "open science"
            assert per_page == 1
            return SearchResponse(
                query=query,
                source="openalex",
                total_results=1,
                per_page=per_page,
                results=[
                    PaperResult(
                        source="openalex",
                        title="Open science result",
                        source_url="https://openalex.org/W1",
                    )
                ],
            )

    message, details = await check.run_anonymous_openalex_search(
        query="open science", per_page=1, client_factory=FakeClient
    )

    assert message == "anonymous OpenAlex search returned 1 result(s)"
    assert details["credential_mode"] == "anonymous"
    assert details["first_url"] == "https://openalex.org/W1"
    assert FakeClient.closed is True


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "openalex.json"
    markdown_report = tmp_path / "openalex.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/openalex_functional_check.py",
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
    assert report["script"] == "openalex_functional_check"
    assert report["mode"] == "offline"
    assert report["overall"] == "SKIP"
    assert report["environment"]["credential_mode"] == "anonymous"
    assert markdown_report.exists()


def test_live_mode_requires_explicit_execute_flag() -> None:
    with pytest.raises(SystemExit, match="2"):
        asyncio.run(check.main(["--mode", "live"]))
