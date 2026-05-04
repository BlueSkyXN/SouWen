from __future__ import annotations

import json
import subprocess

import pytest

from scripts.ci import run_profile
from scripts._functional_common import Outcome


def test_list_profiles(capsys):
    assert run_profile.main(["--list-profiles"]) == 0

    output = capsys.readouterr().out
    assert "minimal" in output
    assert "server" in output
    assert "full" in output
    assert "plugin" in output


def test_main_requires_profile():
    with pytest.raises(SystemExit) as exc_info:
        run_profile.main([])

    assert exc_info.value.code == 2


def test_run_profiles_records_success(monkeypatch, tmp_path):
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    json_report = tmp_path / "profile.json"
    markdown_report = tmp_path / "profile.md"
    exit_code = run_profile.main(
        [
            "--profile",
            "minimal",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ]
    )

    assert exit_code == 0
    assert len(calls) == len(run_profile.PROFILE_COMMANDS["minimal"])
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["script"] == "ci_profile_runner"
    assert payload["mode"] == "minimal"
    assert payload["overall"] == "PASS"
    assert payload["checks"][0]["name"].startswith("minimal/")
    assert "Overall: **PASS**" in markdown_report.read_text(encoding="utf-8")


def test_required_command_failure_sets_overall_fail(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="boom")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["server"], timeout=1)

    assert recorder.overall == Outcome.FAIL
    assert recorder.exit_code() == 1
    assert recorder.checks[0].message == "exit code 2"
    assert recorder.checks[0].details["stderr_tail"] == "boom"


def test_timeout_is_recorded(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=3, output="partial", stderr="late")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["full"], timeout=3)

    assert recorder.overall == Outcome.FAIL
    assert recorder.checks[0].message == "timeout after 3.0s"
    assert recorder.checks[0].details["stdout_tail"] == "partial"


def test_tail_truncates_from_end():
    assert run_profile._tail("abcdef", limit=3) == "def"
