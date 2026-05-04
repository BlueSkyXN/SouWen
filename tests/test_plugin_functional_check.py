from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts._functional_common import CheckSkipped, CheckWarning
from scripts import plugin_functional_check as check


def test_distribution_version_returns_none_for_missing_distribution() -> None:
    assert check.distribution_version("__definitely_missing_souwen_plugin__") is None


def test_example_distribution_missing_is_skip_when_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: None)

    with pytest.raises(CheckSkipped):
        check.verify_example_distribution(require_installed=False)


def test_example_distribution_missing_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: None)

    with pytest.raises(AssertionError):
        check.verify_example_distribution(require_installed=True)


def test_example_distribution_passes_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: "1.2.3")

    message, details = check.verify_example_distribution(require_installed=True)

    assert "distribution is installed" in message
    assert details["distribution"] == check.EXAMPLE_DISTRIBUTION
    assert details["version"] == "1.2.3"


def test_optional_web2pdf_missing_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: None)

    with pytest.raises(CheckWarning):
        check.verify_optional_web2pdf(require_installed=False)


def test_optional_web2pdf_missing_fails_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: None)

    with pytest.raises(AssertionError):
        check.verify_optional_web2pdf(require_installed=True)


def test_offline_mode_writes_skip_report(tmp_path: Path) -> None:
    json_report = tmp_path / "plugin.json"
    markdown_report = tmp_path / "plugin.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/plugin_functional_check.py",
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
    assert data["script"] == "plugin_functional_check"
    assert data["mode"] == "offline"
    assert data["overall"] == "SKIP"
    assert data["checks"][0]["name"] == "offline_mode"
    assert data["checks"][0]["outcome"] == "SKIP"
    assert "Overall: **SKIP**" in markdown_report.read_text(encoding="utf-8")
