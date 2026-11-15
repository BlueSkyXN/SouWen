"""image.yml 的 souwen_ref 解析必须 fail closed（复核项 2）。

只有真正空的输入才默认 ``github.sha``；非空但不是 40 位 commit SHA 的输入
必须让步骤失败，而不是悄悄发布另一个版本。这里直接执行 workflow 里那段
真实的 shell 脚本，避免测试与实际 workflow 文本漂移。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github/workflows/image.yml"
RESOLVE_STEP = "Resolve SOUWEN_REF (empty input defaults to github.sha)"

DEFAULT_SHA = "0123456789abcdef0123456789abcdef01234567"
EXPLICIT_SHA = "fedcba9876543210fedcba9876543210fedcba98"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _workflow()["jobs"]["build-and-sync"]["steps"]


def _resolve_step() -> dict:
    for step in _steps():
        if step.get("name") == RESOLVE_STEP:
            return step
    raise AssertionError(f"image.yml has no step named {RESOLVE_STEP!r}")


def _run_resolve(tmp_path: Path, input_value: str | None) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "GITHUB_SHA": DEFAULT_SHA,
        "GITHUB_ENV": str(tmp_path / "github_env"),
        "SOUWEN_REF_INPUT": input_value or "",
    }
    return subprocess.run(
        ["bash", "-c", _resolve_step()["run"]],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _resolved_ref(tmp_path: Path) -> str:
    content = (tmp_path / "github_env").read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line.startswith("SOUWEN_REF=")]
    assert len(lines) == 1, f"expected one SOUWEN_REF line, got {content!r}"
    return lines[0].split("=", 1)[1]


def test_empty_input_defaults_to_github_sha(tmp_path: Path):
    result = _run_resolve(tmp_path, "")

    assert result.returncode == 0, result.stderr
    assert _resolved_ref(tmp_path) == DEFAULT_SHA


def test_unset_input_defaults_to_github_sha(tmp_path: Path):
    result = _run_resolve(tmp_path, None)

    assert result.returncode == 0, result.stderr
    assert _resolved_ref(tmp_path) == DEFAULT_SHA


def test_explicit_sha_is_kept_even_when_it_is_not_current(tmp_path: Path):
    result = _run_resolve(tmp_path, EXPLICIT_SHA)

    assert result.returncode == 0, result.stderr
    assert _resolved_ref(tmp_path) == EXPLICIT_SHA


@pytest.mark.parametrize(
    "bad_input",
    [
        "deadbeef",
        "main",
        "agent-first",
        "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
        "a" * 41,
        "a" * 39,
        f"{EXPLICIT_SHA}0",
    ],
)
def test_invalid_non_empty_input_fails_without_writing_the_env(tmp_path: Path, bad_input: str):
    result = _run_resolve(tmp_path, bad_input)

    assert result.returncode != 0, f"{bad_input!r} should not resolve"
    assert "::error::souwen_ref" in result.stdout
    assert not (tmp_path / "github_env").exists()


def test_input_reaches_shell_through_the_environment_not_interpolation():
    step = _resolve_step()

    assert step["env"]["SOUWEN_REF_INPUT"] == "${{ github.event.inputs.souwen_ref }}"
    assert "github.event.inputs.souwen_ref" not in step["run"]


def test_checkout_uses_the_resolved_ref_without_a_second_default():
    checkout = next(
        step for step in _steps() if step.get("uses", "").startswith("actions/checkout")
    )

    assert checkout["with"]["ref"] == "${{ env.SOUWEN_REF }}"


def test_sync_path_is_unreachable_after_a_failed_resolve():
    """resolve 之后的每一步都依赖 env.SOUWEN_REF，不会回落到 HEAD。"""
    steps = _steps()
    resolve_at = steps.index(_resolve_step())

    for step in steps[resolve_at + 1 :]:
        text = step.get("run", "")
        assert "souwen_ref" not in text, f"{step.get('name')} reads the raw input again"
        if step.get("name", "").startswith("Verify checked-out tree"):
            # 空值必须立即失败，而不是 `:-` 回落到 HEAD。
            assert ":-" not in text
            assert "SOUWEN_REF:?" in text
