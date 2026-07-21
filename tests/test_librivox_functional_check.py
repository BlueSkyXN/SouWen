from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import librivox_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder
from souwen.models import (
    Author,
    BookAudioSection,
    BookResult,
    ResourceAccess,
    ResourceLink,
    SearchResponse,
)


def test_verify_librivox_registered_reports_anonymous_explicit_contract() -> None:
    message, details = check.verify_librivox_registered()

    assert message == "librivox registry contract passed"
    assert details == {
        "source": "librivox",
        "domain": "book",
        "capabilities": ["get_detail", "search"],
        "default_for": [],
        "auth_requirement": "none",
        "needs_config": False,
    }


@pytest.mark.asyncio
async def test_search_and_detail_uses_one_same_item_metadata_flow() -> None:
    class FakeClient:
        closed = False
        calls: list[tuple[str, object]] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            FakeClient.closed = True

        async def search(self, query: str, *, per_page: int, search_field: str) -> SearchResponse:
            FakeClient.calls.append(("search", (query, per_page, search_field)))
            return SearchResponse(
                query=query,
                source="librivox",
                total_results=1,
                per_page=per_page,
                results=[
                    BookResult(
                        source="librivox",
                        source_record_id="253",
                        title="Search result",
                        source_url="https://librivox.org/pride-and-prejudice/",
                    )
                ],
            )

        async def get_by_id(self, audiobook_id: str, *, audio_limit: int) -> BookResult:
            FakeClient.calls.append(("get_by_id", (audiobook_id, audio_limit)))
            access = ResourceAccess(status="unknown")
            resource = ResourceLink(
                url="https://archive.org/download/pride/chapter-1.mp3",
                relation="audio",
                media_type="audio/mpeg",
                format="MP3",
                source="librivox",
                access=access,
            )
            return BookResult(
                source="librivox",
                source_record_id=audiobook_id,
                title="Detail result",
                readers=[Author(name="Reader")],
                audio_sections=[
                    BookAudioSection(
                        source_section_id="1",
                        readers=[Author(name="Reader")],
                        resource=resource,
                    )
                ],
                resources=[resource],
                access=access,
                source_url="https://librivox.org/pride-and-prejudice/",
            )

    message, details = await check.run_librivox_search_and_detail(
        query="pride and prejudice",
        per_page=1,
        audio_limit=3,
        search_field="title",
        client_factory=FakeClient,
    )

    assert message == "LibriVox search/detail returned audiobook 253"
    assert details["audio_resource_count"] == 1
    assert details["reader_count"] == 1
    assert details["no_automatic_audio_or_rss_download"] is True
    assert details["rights_law_and_jurisdiction_specific"] is True
    assert FakeClient.calls == [
        ("search", ("pride and prejudice", 1, "title")),
        ("get_by_id", ("253", 3)),
    ]
    assert FakeClient.closed is True


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "librivox.json"
    markdown_report = tmp_path / "librivox.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/librivox_functional_check.py",
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
    assert report["script"] == "librivox_functional_check"
    assert report["mode"] == "offline"
    assert report["overall"] == "SKIP"
    assert report["environment"]["credential_mode"] == "anonymous"
    assert (
        report["environment"]["access_mode"] == "catalog_metadata_and_declared_audio_rss_links_only"
    )
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

    monkeypatch.setattr(check, "verify_librivox_registered", lambda: ("ok", {}))
    monkeypatch.setattr(check, "run_librivox_search_and_detail", failing_live_check)
    recorder = ResultRecorder(script="test", mode="live")
    args = argparse.Namespace(
        mode="live",
        required=required,
        timeout=1.0,
        query="catalog",
        per_page=1,
        audio_limit=1,
        search_field="title",
    )

    await check.run_selected_checks(args, recorder)

    assert recorder.checks[-1].outcome == expected_outcome
    assert recorder.checks[-1].required is required
    assert recorder.exit_code() == expected_exit_code
