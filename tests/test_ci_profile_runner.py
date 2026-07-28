from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.ci import run_profile
from scripts._functional_common import Outcome


REPO_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_RUNTIME_EXTRAS = ".[dev,server,tls,web,robots,scraper,newspaper,readability]"
SERVER_RUNTIME_EXTRAS = ".[dev,server,tls,web,robots,scraper]"
PROFILE_RUNNER_WORKFLOWS = {
    ".github/workflows/ci.yml": ("provider-runtime",),
    ".github/workflows/v2-ci.yml": (
        "sdk-contract",
        "server-contract",
        "provider-runtime",
    ),
    ".github/workflows/deploy-hf-space.yml": ("sdk-contract", "server-contract"),
}
RETIRED_CI_PROFILE_NAMES = (
    "basic-cli",
    "pro-cli",
    "full-cli",
    "minimal",
    "server",
    "full",
)


def test_list_profiles(capsys):
    assert run_profile.main(["--list-profiles"]) == 0

    output = set(capsys.readouterr().out.splitlines())
    assert output == {"sdk-contract", "server-contract", "provider-runtime"}


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
            "sdk-contract",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ]
    )

    assert exit_code == 0
    assert len(calls) == len(run_profile.PROFILE_COMMANDS["sdk-contract"])
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["script"] == "ci_profile_runner"
    assert payload["mode"] == "sdk-contract"
    assert payload["overall"] == "PASS"
    assert payload["checks"][0]["name"].startswith("sdk-contract/")
    assert payload["environment"]["profiles"] == ["sdk-contract"]
    assert "Overall: **PASS**" in markdown_report.read_text(encoding="utf-8")


@pytest.mark.parametrize("profile", RETIRED_CI_PROFILE_NAMES)
def test_retired_profile_names_are_rejected(profile):
    with pytest.raises(SystemExit) as exc_info:
        run_profile.main(["--profile", profile])

    assert exc_info.value.code == 2


def test_required_command_failure_sets_overall_fail(monkeypatch):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="boom")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["server-contract"], timeout=1)

    assert recorder.overall == Outcome.FAIL
    assert recorder.exit_code() == 1
    assert recorder.checks[0].message == "exit code 2"
    assert recorder.checks[0].details["stderr_tail"] == "boom"
    assert recorder.checks[0].name.startswith("server-contract/")


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
            "sdk-contract",
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

    recorder = run_profile.run_profiles(["provider-runtime"], timeout=1)

    assert recorder.overall == Outcome.PASS
    assert captured_env["PYTHONPATH"].split(os.pathsep)[:2] == [
        str(run_profile.SOURCE_ROOT),
        "existing",
    ]
    assert "SOUWEN_EDITION" not in captured_env


def test_provider_runtime_code_uses_manifest_registry_and_target_composition() -> None:
    assert "builtin_provider_manifests" in run_profile.PROVIDER_RUNTIME_CODE
    assert "build_target_runtime" in run_profile.PROVIDER_RUNTIME_CODE
    assert "capability_adapters" not in run_profile.PROVIDER_RUNTIME_CODE
    assert "== 110" in run_profile.PROVIDER_RUNTIME_CODE
    assert "runtime.close" in run_profile.PROVIDER_RUNTIME_CODE


def test_sdk_contract_uses_target_contract_dto_and_openapi_artifact_checks() -> None:
    commands = run_profile.PROFILE_COMMANDS["sdk-contract"]
    command = commands[0].command

    assert "tests/contracts/test_target_canonical_contract.py" in command
    assert "tests/contracts/test_target_openapi_artifact.py" in command
    assert "tests/test_target_canonical_dto.py" in command
    assert not any("provider" in argument for argument in command if argument.startswith("tests/"))
    assert commands[1].name == "openapi_artifact_reproducibility"
    assert commands[1].command == (run_profile.PYTHON, "tools/gen_openapi.py", "--check")
    assert commands[2].name == "openapi_semantic_contract"
    assert commands[2].command == (
        run_profile.PYTHON,
        "tools/gen_openapi.py",
        "--semantic-check",
        "contracts/openapi/souwen-openapi-2.0.0rc3.json",
    )
    assert commands[3].name == "python_sdk_reproducibility"
    assert commands[3].command == (
        run_profile.PYTHON,
        "tools/gen_client_sdk.py",
        "--check",
    )
    assert commands[4].name == "python_sdk_contract"
    assert "tests/test_client_sdk_generator.py" in commands[4].command
    assert "tests/test_client_sdk_contract.py" in commands[4].command
    assert commands[5].name == "typescript_sdk_reproducibility"
    assert commands[5].command == (
        run_profile.PYTHON,
        "tools/gen_typescript_sdk.py",
        "--check",
    )
    assert commands[6].name == "typescript_sdk_contract"
    assert "tests/test_typescript_sdk_generator.py" in commands[6].command


def test_v2_ci_checks_reproducibility_and_pr_semantic_openapi_compatibility() -> None:
    v2_ci = (REPO_ROOT / ".github/workflows/v2-ci.yml").read_text(encoding="utf-8")
    bootstrap = v2_ci.split("  bootstrap:", maxsplit=1)[1].split("  matrix_tests:", maxsplit=1)[0]

    assert "fetch-depth: 0" in bootstrap
    assert 'pip install -e ".[dev,server]"' in bootstrap
    assert "python tools/gen_openapi.py --check" in bootstrap
    assert "python tools/gen_client_sdk.py --check" in bootstrap
    assert "python tools/gen_typescript_sdk.py --check" in bootstrap
    assert "--semantic-check artifacts/openapi-semantic-baseline.json" in bootstrap
    assert "version rollover baseline $previous_artifact" in bootstrap
    assert "contracts/openapi/souwen-openapi-2.0.0rc2.json" in bootstrap
    assert 'git show "$BASE_SHA:$baseline_artifact"' in bootstrap
    assert "initial baseline; base artifact is absent" in bootstrap
    assert 'git cat-file -e "$BASE_SHA:$artifact"' in bootstrap
    assert "approved one-time RC2 target-only OpenAPI cutover" in bootstrap
    assert "7dbb1f88ada692a757a6800754e3adb06166a305" in bootstrap
    assert '"removed_schemas": [' in bootstrap
    assert "tests/test_manifest_registry_v2.py" in bootstrap
    assert "tests/test_provider_manager_v2.py" in bootstrap
    assert "tests/registry/test_consistency.py" not in bootstrap


def test_workflows_install_provider_runtime_extras() -> None:
    for relative in (".github/workflows/ci.yml", ".github/workflows/v2-ci.yml"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")

        assert f'pip install -e "{PROVIDER_RUNTIME_EXTRAS}"' in text


@pytest.mark.parametrize(
    ("relative", "job_name"),
    [
        (".github/workflows/ci.yml", "test"),
        (".github/workflows/ci.yml", "targeted-coverage"),
        (".github/workflows/v2-ci.yml", "matrix_tests"),
    ],
)
def test_full_pytest_jobs_install_pro_runtime(relative: str, job_name: str) -> None:
    """Full and targeted pytest jobs should not silently run without server/runtime extras."""
    workflow = yaml.safe_load((REPO_ROOT / relative).read_text(encoding="utf-8"))
    commands = "\n".join(str(step.get("run", "")) for step in workflow["jobs"][job_name]["steps"])

    assert f'pip install -e "{SERVER_RUNTIME_EXTRAS}"' in commands


def test_ci_workflows_do_not_install_retired_browser_extras() -> None:
    for relative in (".github/workflows/ci.yml", ".github/workflows/v2-ci.yml"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")

        assert "crawl4ai" not in text
        assert "scrapling" not in text
        assert "edition-" not in text


def test_ci_workflows_use_canonical_profile_names() -> None:
    for relative, expected_profiles in PROFILE_RUNNER_WORKFLOWS.items():
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")

        for profile in expected_profiles:
            assert re.search(rf"--profile\s+{re.escape(profile)}(?=$|\s|\\)", text), relative
        for retired_profile in RETIRED_CI_PROFILE_NAMES:
            assert not re.search(rf"--profile\s+{re.escape(retired_profile)}(?=$|\s|\\)", text), (
                relative
            )


def test_ci_workflows_install_server_runtime_extras() -> None:
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    v2_ci = (REPO_ROOT / ".github/workflows/v2-ci.yml").read_text(encoding="utf-8")
    hf_cd = (REPO_ROOT / ".github/workflows/deploy-hf-space.yml").read_text(encoding="utf-8")

    for text in (ci, v2_ci, hf_cd):
        assert 'pip install -e ".[dev,server,tls,web,robots,scraper]"' in text
        assert "edition-" not in text


def test_hf_space_post_deploy_fails_public_admin_open() -> None:
    hf_cd = (REPO_ROOT / ".github/workflows/deploy-hf-space.yml").read_text(encoding="utf-8")

    assert 'SOUWEN_SMOKE_FAIL_ADMIN_OPEN: "1"' in hf_cd
    assert "SOUWEN_SMOKE_BEARER_TOKEN" in hf_cd


def test_agent_command_docs_use_canonical_profile_names() -> None:
    agent_docs = (
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "src/souwen/server/AGENTS.md",
    )

    combined_text = "\n".join(path.read_text(encoding="utf-8") for path in agent_docs)

    for profile in ("sdk-contract", "server-contract", "provider-runtime"):
        assert re.search(rf"--profile\s+{re.escape(profile)}(?=$|\s|`)", combined_text)
    for retired_profile in RETIRED_CI_PROFILE_NAMES:
        assert not re.search(
            rf"--profile\s+{re.escape(retired_profile)}(?=$|\s|`)",
            combined_text,
        )

    assert 'pip install -e ".[dev,server,tls,web,robots,scraper]"' in combined_text
    assert (
        'pip install -e ".[dev,server,tls,web,robots,scraper,newspaper,readability]"'
        in combined_text
    )
    assert "edition-" not in combined_text


def test_timeout_is_recorded(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=3, output="partial", stderr="late")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(["provider-runtime"], timeout=3)

    assert recorder.overall == Outcome.FAIL
    assert recorder.checks[0].message == "timeout after 3.0s"
    assert recorder.checks[0].details["stdout_tail"] == "partial"


def test_canonical_profiles_do_not_set_edition_environment(monkeypatch):
    captured: list[str | None] = []

    def fake_run(command, **kwargs):
        captured.append(kwargs["env"].get("SOUWEN_EDITION"))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(run_profile, "_run_subprocess", fake_run)

    recorder = run_profile.run_profiles(
        ["sdk-contract", "server-contract", "provider-runtime"], timeout=1
    )

    assert recorder.overall == Outcome.PASS
    assert {check.name.split("/", maxsplit=1)[0] for check in recorder.checks} == {
        "sdk-contract",
        "server-contract",
        "provider-runtime",
    }
    expected_command_count = sum(
        len(run_profile.PROFILE_COMMANDS[profile])
        for profile in ("sdk-contract", "server-contract", "provider-runtime")
    )
    assert captured == [None] * expected_command_count


def test_tail_truncates_from_end():
    assert run_profile._tail("abcdef", limit=3) == "def"
