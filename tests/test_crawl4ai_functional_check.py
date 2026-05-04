from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts._functional_common import CheckSkipped
from scripts.crawl4ai_functional_check import (
    looks_like_runtime_missing,
    verify_real_crawl4ai_import,
)


def test_runtime_missing_error_detection() -> None:
    assert looks_like_runtime_missing("Executable doesn't exist at /tmp/chromium")
    assert looks_like_runtime_missing("Please run python -m playwright install")
    assert not looks_like_runtime_missing("HTTP 500 from fixture")
    assert not looks_like_runtime_missing(None)


def test_import_missing_is_skip_when_runtime_not_required(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "crawl4ai":
            raise ImportError("missing crawl4ai")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(CheckSkipped):
        verify_real_crawl4ai_import(require_runtime=False)


def test_import_missing_fails_when_runtime_required(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "crawl4ai":
            raise ImportError("missing crawl4ai")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ImportError):
        verify_real_crawl4ai_import(require_runtime=True)


def test_offline_mode_writes_skip_report(tmp_path: Path) -> None:
    json_report = tmp_path / "crawl4ai.json"
    markdown_report = tmp_path / "crawl4ai.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/crawl4ai_functional_check.py",
            "--mode",
            "offline",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "SKIP offline_mode" in completed.stdout
    data = json.loads(json_report.read_text(encoding="utf-8"))
    assert data["script"] == "crawl4ai_functional_check"
    assert data["mode"] == "offline"
    assert data["overall"] == "SKIP"
    assert data["checks"][0]["name"] == "offline_mode"
    assert data["checks"][0]["outcome"] == "SKIP"
    assert "Overall: **SKIP**" in markdown_report.read_text(encoding="utf-8")
