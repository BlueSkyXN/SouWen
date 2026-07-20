from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from scripts.ci import run_profile
from scripts._functional_common import Outcome


REPO_ROOT = Path(__file__).resolve().parents[1]
FULL_PROFILE_EXTRAS = ".[dev,edition-full]"
EXTERNAL_RUNTIME_WORKFLOWS = (
    ".github/workflows/ci.yml",
    ".github/workflows/external-smoke-gate.yml",
)
PROFILE_RUNNER_WORKFLOWS = {
    ".github/workflows/ci.yml": ("full-cli",),
    ".github/workflows/v2-ci.yml": ("pro-cli", "basic-cli", "full-cli"),
    ".github/workflows/deploy-hf-space.yml": ("pro-cli", "basic-cli"),
}
LEGACY_CI_PROFILE_NAMES = ("minimal", "server", "full")


def test_list_profiles(capsys):
    assert run_profile.main(["--list-profiles"]) == 0

    output = set(capsys.readouterr().out.splitlines())
    assert {"basic-cli", "pro-cli", "full-cli", "plugin"} <= output
    assert {"minimal", "server", "full"} <= output


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
            "basic-cli",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ]
    )

    assert exit_code == 0
    assert len(calls) == len(run_profile.PROFILE_COMMANDS["basic-cli"])
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["script"] == "ci_profile_runner"
    assert payload["mode"] == "basic-cli"
    assert payload["overall"] == "PASS"
    assert payload["checks"][0]["name"].startswith("basic-cli/")
    assert payload["environment"]["profiles"] == ["basic-cli"]
    assert "Overall: **PASS**" in markdown_report.read_text(encoding="utf-8")


def test_legacy_alias_runs_canonical_profile_but_preserves_report_name(monkeypatch):
    calls: list[tuple[str, ...]] = []
    editions: list[str] = []

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        editions.append(kwargs["env"]["SOUWEN_EDITION"])
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["minimal"], timeout=1)

    assert recorder.overall == Outcome.PASS
    assert len(calls) == len(run_profile.PROFILE_COMMANDS["basic-cli"])
    assert {check.name.split("/", maxsplit=1)[0] for check in recorder.checks} == {"minimal"}
    assert set(editions) == {"basic"}
    assert recorder.to_json()["mode"] == "minimal"
    assert recorder.to_json()["environment"]["profiles"] == ["minimal"]


def test_required_command_failure_sets_overall_fail(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="boom")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["server"], timeout=1)

    assert recorder.overall == Outcome.FAIL
    assert recorder.exit_code() == 1
    assert recorder.checks[0].message == "exit code 2"
    assert recorder.checks[0].details["stderr_tail"] == "boom"
    assert recorder.checks[0].name.startswith("server/")


def test_main_returns_two_when_report_write_fails(monkeypatch, tmp_path, capsys):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    def fail_write_reports(self, *, json_report=None, markdown_report=None):
        raise OSError("disk full")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)
    monkeypatch.setattr(run_profile.ResultRecorder, "write_reports", fail_write_reports)

    exit_code = run_profile.main(
        [
            "--profile",
            "basic-cli",
            "--json-report",
            str(tmp_path / "profile.json"),
        ]
    )

    assert exit_code == 2
    assert "failed to write CI profile reports: disk full" in capsys.readouterr().err


def test_profile_commands_prepend_source_pythonpath(monkeypatch):
    captured_env: dict[str, str] = {}

    def fake_run(command, **kwargs):
        captured_env.update(kwargs["env"])
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setenv("PYTHONPATH", "existing")
    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["full-cli"], timeout=1)

    assert recorder.overall == Outcome.PASS
    assert captured_env["PYTHONPATH"].split(os.pathsep)[:2] == [
        str(run_profile.SOURCE_ROOT),
        "existing",
    ]
    assert captured_env["SOUWEN_EDITION"] == "full"


def test_full_import_code_covers_full_fetch_provider_modules() -> None:
    assert run_profile.FULL_FETCH_PROVIDER_MODULES == {
        "arxiv_fulltext": "souwen.paper.arxiv_fulltext",
        "crawl4ai": "souwen.web.crawl4ai_fetcher",
        "newspaper": "souwen.web.newspaper_fetcher",
        "readability": "souwen.web.readability_fetcher",
        "scrapling": "souwen.web.scrapling_fetcher",
    }

    assert "declared_fetch_provider_names" in run_profile.FULL_IMPORT_CODE
    assert "probe_capabilities" in run_profile.FULL_IMPORT_CODE
    for provider, module in run_profile.FULL_FETCH_PROVIDER_MODULES.items():
        assert provider in run_profile.FULL_IMPORT_CODE
        assert module in run_profile.FULL_IMPORT_CODE


def test_workflows_install_full_profile_runtime_extras() -> None:
    for relative in (".github/workflows/ci.yml", ".github/workflows/v2-ci.yml"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")

        assert f'pip install -e "{FULL_PROFILE_EXTRAS}"' in text


def test_external_runtime_workflows_install_edition_extras() -> None:
    for relative in EXTERNAL_RUNTIME_WORKFLOWS:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")

        assert 'pip install -e ".[dev,edition-full-scrapling]"' in text
        assert 'pip install -e ".[dev,edition-full-crawl4ai]"' in text
        assert 'pip install -e ".[dev,edition-full]"' in text
        assert 'pip install -e ".[dev,server,scrapling]"' not in text
        assert 'pip install -e ".[dev,server,crawl4ai]"' not in text
        assert 'pip install -e ".[dev,server,newspaper,readability]"' not in text


def test_ci_workflows_use_canonical_profile_names() -> None:
    for relative, expected_profiles in PROFILE_RUNNER_WORKFLOWS.items():
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")

        for profile in expected_profiles:
            assert re.search(rf"--profile\s+{re.escape(profile)}(?=$|\s|\\)", text), relative
        for legacy_profile in LEGACY_CI_PROFILE_NAMES:
            assert not re.search(rf"--profile\s+{re.escape(legacy_profile)}(?=$|\s|\\)", text), (
                relative
            )


def test_ci_workflows_install_edition_profile_extras() -> None:
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    v2_ci = (REPO_ROOT / ".github/workflows/v2-ci.yml").read_text(encoding="utf-8")
    hf_cd = (REPO_ROOT / ".github/workflows/deploy-hf-space.yml").read_text(encoding="utf-8")

    for text in (ci, v2_ci, hf_cd):
        assert 'pip install -e ".[dev,edition-pro]"' in text
        assert 'pip install -e ".[dev,server]"' not in text
        assert 'pip install -e ".[dev,server,tls]"' not in text


def test_hf_space_post_deploy_fails_public_admin_open() -> None:
    hf_cd = (REPO_ROOT / ".github/workflows/deploy-hf-space.yml").read_text(encoding="utf-8")

    assert 'SOUWEN_SMOKE_FAIL_ADMIN_OPEN: "1"' in hf_cd
    assert "SOUWEN_SMOKE_BEARER_TOKEN" in hf_cd


def test_agent_command_docs_use_canonical_profile_names() -> None:
    agent_docs = (
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "src/souwen/cli/AGENTS.md",
        REPO_ROOT / "src/souwen/server/AGENTS.md",
    )

    combined_text = "\n".join(path.read_text(encoding="utf-8") for path in agent_docs)

    for profile in ("basic-cli", "pro-cli", "full-cli"):
        assert re.search(rf"--profile\s+{re.escape(profile)}(?=$|\s|`)", combined_text)
    for legacy_profile in LEGACY_CI_PROFILE_NAMES:
        assert not re.search(
            rf"--profile\s+{re.escape(legacy_profile)}(?=$|\s|`)",
            combined_text,
        )

    assert 'pip install -e ".[dev,edition-pro]"' in combined_text
    assert 'pip install -e ".[dev,edition-full]"' in combined_text
    assert 'pip install -e ".[dev,server]"' not in combined_text
    assert "server,tls,web,scraper,newspaper,readability,pdf,mcp" not in combined_text


def test_timeout_is_recorded(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=3, output="partial", stderr="late")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["full-cli"], timeout=3)

    assert recorder.overall == Outcome.FAIL
    assert recorder.checks[0].message == "timeout after 3.0s"
    assert recorder.checks[0].details["stdout_tail"] == "partial"


def test_canonical_profile_editions_are_explicit(monkeypatch):
    captured: dict[str, str] = {}

    def fake_run(command, **kwargs):
        if command[:2] == (run_profile.PYTHON, "-c"):
            profile = command[-1]
        elif command[:3] == (run_profile.PYTHON, "-m", "pytest"):
            profile = "pytest"
        else:
            profile = command[1]
        captured[profile] = kwargs["env"]["SOUWEN_EDITION"]
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["basic-cli", "pro-cli", "full-cli"], timeout=1)

    assert recorder.overall == Outcome.PASS
    assert {check.name.split("/", maxsplit=1)[0] for check in recorder.checks} == {
        "basic-cli",
        "pro-cli",
        "full-cli",
    }
    assert captured["cli.py"] == "basic"
    assert captured["pytest"] == "pro"
    assert captured[run_profile.FULL_IMPORT_CODE] == "full"


def test_tail_truncates_from_end():
    assert run_profile._tail("abcdef", limit=3) == "def"
