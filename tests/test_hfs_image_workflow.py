"""Execute the real hfs-image workflow steps with a fake docker (复核 R2).

The review showed that the whole WARP step used continue-on-error, so an
implementation failure after the proxy came up was reported as "WARP
registration unavailable", and that a failing probe skipped the report copy.
These tests run the actual `run:` scripts from `.github/workflows/ci.yml`
against a fake docker binary; only the external process is replaced.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

WARP_STEP = "Check the real WARP exit and the proxied browser path"
CLASSIFY_STEP = "Classify the WARP leg result"
HTTP_STEP = "Check HTTP search and fetch"

_PASSING_WARP_REPORT = {
    "schema_version": 1,
    "script": "hfs_image_check:warp",
    "overall": "PASS",
    "checks": [
        {"name": "warp.socks_egress", "outcome": "PASS", "required": True, "details": {}},
        {"name": "warp.exit_differs", "outcome": "PASS", "required": True, "details": {}},
        {
            "name": "warp.actual_mode",
            "outcome": "PASS",
            "required": True,
            "details": {"mode": "usque", "status": "enabled"},
        },
        {"name": "warp.browser_via_warp", "outcome": "PASS", "required": True, "details": {}},
        {"name": "warp.mcp_after_warp", "outcome": "PASS", "required": True, "details": {}},
        {"name": "warp.http_after_warp", "outcome": "PASS", "required": True, "details": {}},
    ],
}

_BROWSER_FAILURE_REPORT = {
    "schema_version": 1,
    "script": "hfs_image_check:warp",
    "overall": "FAIL",
    "checks": [
        {"name": "warp.socks_egress", "outcome": "PASS", "required": True, "details": {}},
        {"name": "warp.exit_differs", "outcome": "PASS", "required": True, "details": {}},
        {
            "name": "warp.actual_mode",
            "outcome": "PASS",
            "required": True,
            "details": {"mode": "usque", "status": "enabled"},
        },
        {
            "name": "warp.browser_via_warp",
            "outcome": "FAIL",
            "required": True,
            "details": {"exception_type": "ProbeError"},
        },
        {"name": "warp.mcp_after_warp", "outcome": "PASS", "required": True, "details": {}},
        {"name": "warp.http_after_warp", "outcome": "PASS", "required": True, "details": {}},
    ],
}

_EXTERNAL_UNAVAILABLE_REPORT = {
    "schema_version": 1,
    "script": "hfs_image_check:warp",
    "overall": "FAIL",
    "checks": [
        {
            "name": "warp.socks_egress",
            "outcome": "FAIL",
            "required": True,
            "details": {
                "history": [{"attempt": 1, "error": "ConnectError"}],
                "warp_state": {"state_file": "missing"},
            },
        },
        {
            "name": "warp.exit_differs",
            "outcome": "FAIL",
            "required": True,
            "details": {"exception_type": "ProbeError"},
        },
        {
            "name": "warp.actual_mode",
            "outcome": "FAIL",
            "required": True,
            "details": {"exception_type": "ProbeError"},
        },
        {
            "name": "warp.browser_via_warp",
            "outcome": "FAIL",
            "required": True,
            "details": {"exception_type": "ProbeError"},
        },
        {
            "name": "warp.mcp_after_warp",
            "outcome": "FAIL",
            "required": True,
            "details": {"exception_type": "ProbeError"},
        },
        {
            "name": "warp.http_after_warp",
            "outcome": "FAIL",
            "required": True,
            "details": {"exception_type": "ProbeError"},
        },
    ],
}


def _steps() -> dict[str, str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = {}
    for step in workflow["jobs"]["hfs-image"]["steps"]:
        if isinstance(step, dict) and step.get("name") and step.get("run"):
            steps[step["name"]] = step["run"]
    return steps


def _fake_docker(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / "docker"
    path.write_text(
        """#!/usr/bin/env bash
set -u
command="$1"; shift
case "$command" in
  exec)
    # Map container /tmp paths into FAKE_TMP so tests never share /tmp state.
    report=""
    prev=""
    for arg in "$@"; do
      if [ "$prev" = "--json-report" ]; then report="$FAKE_TMP/$(basename "$arg")"; fi
      prev="$arg"
    done
    if [ -n "${FAKE_REPORT_BODY:-}" ]; then
      printf '%s' "$FAKE_REPORT_BODY" > "$report"
    fi
    exit "${FAKE_PROBE_EXIT:-0}"
    ;;
  cp)
    src="$1"; dst="$2"
    cp "$FAKE_TMP/$(basename "${src#*:}")" "$dst"
    exit 0
    ;;
  *) exit 0 ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _run_step(
    script: str,
    workdir: Path,
    *,
    probe_exit: int,
    report: dict | None,
    keep_going: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = f"{workdir / 'bin'}:{env['PATH']}"
    env["REPORTS"] = str(workdir / "reports")
    env["GITHUB_STEP_SUMMARY"] = str(workdir / "summary.md")
    env["HFS_PORT"] = "49265"
    env["HFS_SMOKE_PASSWORD"] = "smoke-password"
    env["HFS_KEEP_GOING"] = "1" if keep_going else "0"
    env["FAKE_PROBE_EXIT"] = str(probe_exit)
    env["FAKE_REPORT_BODY"] = json.dumps(report) if report is not None else ""
    container_tmp = workdir / "container-tmp"
    container_tmp.mkdir(parents=True, exist_ok=True)
    env["FAKE_TMP"] = str(container_tmp)
    (workdir / "reports").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _summary(workdir: Path) -> str:
    return (workdir / "summary.md").read_text(encoding="utf-8")


class TestReportCollectionSurvivesAFailingProbe:
    """探针失败也要先复制报告：此前 set -e 会在 docker cp 之前退出。"""

    def test_a_failing_http_probe_still_copies_its_report(self, tmp_path):
        _fake_docker(tmp_path / "bin")
        result = _run_step(
            _steps()[HTTP_STEP],
            tmp_path,
            probe_exit=1,
            report={
                "schema_version": 1,
                "overall": "FAIL",
                "checks": [
                    {"name": "http.search", "outcome": "FAIL", "required": True, "details": {}}
                ],
            },
            keep_going=False,
        )

        assert result.returncode == 1
        assert (tmp_path / "reports" / "http.json").is_file()
        assert "probe exited with status 1" in result.stdout


class TestWarpLegClassification:
    def test_all_green_reads_as_pass(self, tmp_path):
        _fake_docker(tmp_path / "bin")
        steps = _steps()
        probe = _run_step(steps[WARP_STEP], tmp_path, probe_exit=0, report=_PASSING_WARP_REPORT)
        verdict = _run_step(steps[CLASSIFY_STEP], tmp_path, probe_exit=0, report=None)

        assert probe.returncode == 0
        assert (tmp_path / "reports" / "warp.json").is_file()
        assert verdict.returncode == 0
        assert "WARP leg verdict (warp): **PASS**" in _summary(tmp_path)

    def test_a_browser_failure_after_the_proxy_came_up_fails_the_job(self, tmp_path):
        _fake_docker(tmp_path / "bin")
        steps = _steps()
        probe = _run_step(steps[WARP_STEP], tmp_path, probe_exit=1, report=_BROWSER_FAILURE_REPORT)
        verdict = _run_step(steps[CLASSIFY_STEP], tmp_path, probe_exit=0, report=None)

        assert probe.returncode == 0  # HFS_KEEP_GOING: the report is kept
        assert (tmp_path / "reports" / "warp.json").is_file()
        assert verdict.returncode == 1
        assert "WARP leg verdict (warp): **FAIL**" in _summary(tmp_path)
        assert "warp.browser_via_warp" in _summary(tmp_path)

    def test_external_registration_failure_is_unverified_not_failed(self, tmp_path):
        _fake_docker(tmp_path / "bin")
        steps = _steps()
        probe = _run_step(
            steps[WARP_STEP], tmp_path, probe_exit=1, report=_EXTERNAL_UNAVAILABLE_REPORT
        )
        verdict = _run_step(steps[CLASSIFY_STEP], tmp_path, probe_exit=0, report=None)

        assert probe.returncode == 0
        assert (tmp_path / "reports" / "warp.json").is_file()
        assert verdict.returncode == 0
        assert "WARP leg verdict (warp): **UNVERIFIED**" in _summary(tmp_path)
        assert "unverified, not passed" in _summary(tmp_path)

    def test_a_missing_report_fails_instead_of_passing_silently(self, tmp_path):
        _fake_docker(tmp_path / "bin")
        steps = _steps()
        probe = _run_step(steps[WARP_STEP], tmp_path, probe_exit=1, report=None)
        verdict = _run_step(steps[CLASSIFY_STEP], tmp_path, probe_exit=0, report=None)

        assert probe.returncode == 0
        assert not (tmp_path / "reports" / "warp.json").exists()
        assert verdict.returncode == 1
        assert "missing or corrupt" in _summary(tmp_path)
