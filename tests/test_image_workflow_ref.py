"""image.yml 的 souwen_ref 解析必须 fail closed（复核项 2）。

只有真正空的输入才默认 ``github.sha``；非空输入必须整体恰好是 40 位十六进制
commit SHA，前后空白、tab、CRLF、嵌入换行或附加变量行一律失败，且失败时不写
``GITHUB_ENV``。接受后统一小写，checkout / verify / 构建 / ref 注入共用这一个
规范值。这里直接执行 workflow 里那段真实的 shell 脚本，避免测试与实际
workflow 文本漂移。
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
VERIFY_STEP = "Verify checked-out tree matches SOUWEN_REF"

DEFAULT_SHA = "0123456789abcdef0123456789abcdef01234567"
EXPLICIT_SHA = "fedcba9876543210fedcba9876543210fedcba98"
UPPER_SHA = EXPLICIT_SHA.upper()
MIXED_SHA = "FeDcBa9876543210fedcba9876543210fedcba98"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _workflow()["jobs"]["build-and-sync"]["steps"]


def _step(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"image.yml has no step named {name!r}")


def _resolve_step() -> dict:
    return _step(RESOLVE_STEP)


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


def _env_file(tmp_path: Path) -> Path:
    return tmp_path / "github_env"


def _env_lines(tmp_path: Path) -> list[str]:
    return _env_file(tmp_path).read_text(encoding="utf-8").splitlines()


def _resolved_ref(tmp_path: Path) -> str:
    lines = [line for line in _env_lines(tmp_path) if line.startswith("SOUWEN_REF=")]
    assert len(lines) == 1, f"expected one SOUWEN_REF line, got {_env_lines(tmp_path)!r}"
    return lines[0].split("=", 1)[1]


def _write_git_shim(tmp_path: Path, head_sha: str) -> Path:
    """A fake ``git`` whose ``rev-parse HEAD`` prints the given SHA."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    shim = bindir / "git"
    shim.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        f"  rev-parse) printf '%s\\n' '{head_sha}' ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return bindir


def _run_verify(tmp_path: Path, ref: str | None, head_sha: str) -> subprocess.CompletedProcess[str]:
    bindir = _write_git_shim(tmp_path, head_sha)
    env = {
        "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
        "GITHUB_ENV": str(_env_file(tmp_path)),
    }
    if ref is not None:
        env["SOUWEN_REF"] = ref
    return subprocess.run(
        ["bash", "-c", _step(VERIFY_STEP)["run"]],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# --- 空输入走默认 ---------------------------------------------------------


def test_empty_input_defaults_to_github_sha(tmp_path: Path):
    result = _run_resolve(tmp_path, "")

    assert result.returncode == 0, result.stderr
    assert _env_lines(tmp_path) == [f"SOUWEN_REF={DEFAULT_SHA}"]


def test_unset_input_defaults_to_github_sha(tmp_path: Path):
    result = _run_resolve(tmp_path, None)

    assert result.returncode == 0, result.stderr
    assert _env_lines(tmp_path) == [f"SOUWEN_REF={DEFAULT_SHA}"]


# --- 合法非当前 SHA -------------------------------------------------------


def test_explicit_sha_is_kept_even_when_it_is_not_current(tmp_path: Path):
    result = _run_resolve(tmp_path, EXPLICIT_SHA)

    assert result.returncode == 0, result.stderr
    assert _env_lines(tmp_path) == [f"SOUWEN_REF={EXPLICIT_SHA}"]


# --- 大小写归一 -----------------------------------------------------------


@pytest.mark.parametrize("input_sha", [UPPER_SHA, MIXED_SHA])
def test_uppercase_input_is_normalised_to_lowercase(tmp_path: Path, input_sha: str):
    result = _run_resolve(tmp_path, input_sha)

    assert result.returncode == 0, result.stderr
    assert _env_lines(tmp_path) == [f"SOUWEN_REF={EXPLICIT_SHA}"]


# --- 非法非空输入 ---------------------------------------------------------


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
        f" {EXPLICIT_SHA}",
        f"{EXPLICIT_SHA} ",
        f"\t{EXPLICIT_SHA}",
        f"{EXPLICIT_SHA}\t",
        f"{EXPLICIT_SHA}\n",
        f"\n{EXPLICIT_SHA}",
        f"{EXPLICIT_SHA}\r\n",
        f"{EXPLICIT_SHA}\nREVIEW_SENTINEL=1",
        f"{EXPLICIT_SHA}\r\nREVIEW_SENTINEL=1",
        f"REVIEW_SENTINEL=1\n{EXPLICIT_SHA}",
        f"{EXPLICIT_SHA}\n{EXPLICIT_SHA}",
    ],
)
def test_invalid_non_empty_input_fails_without_writing_the_env(tmp_path: Path, bad_input: str):
    result = _run_resolve(tmp_path, bad_input)

    assert result.returncode != 0, f"{bad_input!r} should not resolve"
    assert "::error::souwen_ref" in result.stdout
    assert not _env_file(tmp_path).exists()


@pytest.mark.parametrize(
    "bad_input",
    [
        f"{EXPLICIT_SHA}\nREVIEW_SENTINEL=1",
        f"{EXPLICIT_SHA}\r\nREVIEW_SENTINEL=1",
        f"{EXPLICIT_SHA}\n",
    ],
)
def test_failure_does_not_echo_the_raw_multiline_input(tmp_path: Path, bad_input: str):
    result = _run_resolve(tmp_path, bad_input)

    assert result.returncode != 0
    assert "REVIEW_SENTINEL" not in result.stdout
    assert "REVIEW_SENTINEL" not in result.stderr
    # 输入本身不得被整段回显；只允许报告长度。
    assert EXPLICIT_SHA not in result.stdout


def test_whitespace_is_rejected_rather_than_trimmed(tmp_path: Path):
    """前后空格不做静默裁剪：裁剪会让 "  <sha>" 变成合法输入。"""
    result = _run_resolve(tmp_path, f"  {EXPLICIT_SHA}  ")

    assert result.returncode != 0
    assert not _env_file(tmp_path).exists()


# --- resolve 与 verify 的连接 ---------------------------------------------


@pytest.mark.parametrize("input_sha", [EXPLICIT_SHA, UPPER_SHA, MIXED_SHA])
def test_verify_accepts_the_resolved_ref_for_any_input_case(tmp_path: Path, input_sha: str):
    """大写输入 resolve 后是小写，verify 用同一个值必须通过（原缺陷点）。"""
    assert _run_resolve(tmp_path, input_sha).returncode == 0
    resolved = _resolved_ref(tmp_path)

    result = _run_verify(tmp_path, resolved, head_sha=EXPLICIT_SHA)

    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_still_rejects_a_tree_that_differs_from_the_ref(tmp_path: Path):
    assert _run_resolve(tmp_path, EXPLICIT_SHA).returncode == 0
    resolved = _resolved_ref(tmp_path)

    result = _run_verify(tmp_path, resolved, head_sha=DEFAULT_SHA)

    assert result.returncode != 0
    assert "checkout mismatch" in result.stdout


def test_verify_requires_a_resolved_ref_instead_of_falling_back(tmp_path: Path):
    result = _run_verify(tmp_path, None, head_sha=EXPLICIT_SHA)

    assert result.returncode != 0
    assert "SOUWEN_REF must be resolved" in result.stderr


# --- workflow 结构约束 ----------------------------------------------------


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


def test_ref_injection_uses_the_same_resolved_value():
    sync = _step("Sync selected SHA source to HFS Space")["run"]

    assert "${SOUWEN_REF}" in sync
    assert "souwen_ref" not in sync
