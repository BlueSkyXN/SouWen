from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import wikisource_functional_check as check
from scripts._functional_common import Outcome, ResultRecorder
from souwen.models import BookResult, WikisourcePage


def _detail() -> WikisourcePage:
    return WikisourcePage.model_validate(
        {
            "language": "zh",
            "site_url": "https://zh.wikisource.org",
            "page_id": 101,
            "title": "論語",
            "canonical_title": "論語",
            "source_url": "https://zh.wikisource.org/wiki/%E8%AB%96%E8%AA%9E",
            "revision": {
                "revision_id": 202,
                "timestamp": "2024-01-01T00:00:00Z",
                "content": "仁者愛人",
                "content_format": "text",
            },
            "site_content_access": {"status": "unknown"},
            "source_work_access": {"status": "unknown"},
        }
    )


def test_verify_wikisource_registered_reports_anonymous_explicit_contract() -> None:
    message, details = check.verify_wikisource_registered()

    assert message == "wikisource registry contract passed"
    assert details == {
        "source": "wikisource",
        "domain": "book",
        "capabilities": ["get_detail", "search"],
        "default_for": [],
        "auth_requirement": "none",
        "needs_config": False,
        "language_allowlist": ["zh", "en"],
    }


@pytest.mark.asyncio
async def test_search_and_detail_uses_one_bounded_chinese_page_client_flow() -> None:
    class FakeClient:
        closed = False
        calls: list[tuple[str, object]] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            FakeClient.closed = True

        async def search(self, query: str, *, per_page: int, language: str):
            FakeClient.calls.append(("search", (query, per_page, language)))
            return type(
                "Response",
                (),
                {
                    "source": "wikisource",
                    "results": [
                        BookResult(
                            source="wikisource",
                            source_record_id="zh:101",
                            title="論語",
                            source_url="https://zh.wikisource.org/wiki/%E8%AB%96%E8%AA%9E",
                        )
                    ],
                },
            )()

        async def get_page_detail(self, title: str, **kwargs: object) -> WikisourcePage:
            FakeClient.calls.append(("get_page_detail", (title, kwargs)))
            return _detail()

    message, details = await check.run_wikisource_search_and_detail(
        query="論語", per_page=1, max_content_chars=20, client_factory=FakeClient
    )

    assert message == "Wikisource search/detail returned page 論語"
    assert details["page_id"] == 101
    assert details["revision_id"] == 202
    assert details["returned_subpages"] == 0
    assert details["no_dump_recursive_fetch_or_write"] is True
    assert FakeClient.calls == [
        ("search", ("論語", 1, "zh")),
        (
            "get_page_detail",
            (
                "論語",
                {
                    "language": "zh",
                    "content_format": "text",
                    "max_content_chars": 20,
                    "include_subpages": False,
                },
            ),
        ),
    ]
    assert FakeClient.closed is True


def test_offline_mode_writes_skip_report_without_network(tmp_path: Path) -> None:
    json_report = tmp_path / "wikisource.json"
    markdown_report = tmp_path / "wikisource.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/wikisource_functional_check.py",
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
    assert report["script"] == "wikisource_functional_check"
    assert report["mode"] == "offline"
    assert report["overall"] == "SKIP"
    assert report["environment"]["credential_mode"] == "anonymous"
    assert report["environment"]["language"] == "zh"
    assert report["environment"]["access_mode"] == "one_bounded_page_and_revision_only"
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
    async def failing_live_check(**_kwargs: object):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(check, "verify_wikisource_registered", lambda: ("ok", {}))
    monkeypatch.setattr(check, "run_wikisource_search_and_detail", failing_live_check)
    recorder = ResultRecorder(script="test", mode="live")
    args = argparse.Namespace(
        mode="live",
        required=required,
        timeout=1.0,
        query="論語",
        per_page=1,
        max_content_chars=20,
    )

    await check.run_selected_checks(args, recorder)

    assert recorder.checks[-1].outcome == expected_outcome
    assert recorder.checks[-1].required is required
    assert recorder.exit_code() == expected_exit_code
