"""Run deterministic CI profiles and emit machine-readable reports."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src"
for _path in (REPO_ROOT, SOURCE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts._functional_common import Outcome, ResultRecorder  # noqa: E402


DEFAULT_TIMEOUT_SECONDS = 300.0
OUTPUT_TAIL_CHARS = 4000
PYTHON = sys.executable or "python"
PROVIDER_RUNTIME_CODE = "\n".join(
    [
        "import asyncio",
        "from souwen.config import SouWenConfig",
        "from souwen.providers.catalog import builtin_provider_manifests",
        "from souwen.server.v2_runtime import build_target_runtime",
        "manifests = builtin_provider_manifests()",
        "runtime = build_target_runtime(SouWenConfig())",
        "assert {item.id for item in runtime.manager.registry.packages} == "
        "{item.id for item in manifests}",
        "assert sum(len(item.adapters) for item in manifests) == 110",
        "asyncio.run(runtime.close())",
        "print('Provider v2 manifests and runtime composition OK')",
    ]
)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    command: tuple[str, ...]
    required: bool = True
    env: tuple[tuple[str, str], ...] = ()


PROFILE_COMMANDS: Mapping[str, tuple[CommandSpec, ...]] = {
    "sdk-contract": (
        CommandSpec(
            "canonical_contract",
            (
                PYTHON,
                "-m",
                "pytest",
                "tests/contracts/test_target_canonical_contract.py",
                "tests/contracts/test_target_openapi_artifact.py",
                "tests/test_target_canonical_dto.py",
                "-v",
                "--tb=short",
            ),
        ),
        CommandSpec(
            "openapi_artifact_reproducibility",
            (PYTHON, "tools/gen_openapi.py", "--check"),
        ),
        CommandSpec(
            "openapi_semantic_contract",
            (
                PYTHON,
                "tools/gen_openapi.py",
                "--semantic-check",
                "contracts/openapi/souwen-openapi-2.0.0rc6.json",
            ),
        ),
        CommandSpec(
            "python_sdk_reproducibility",
            (PYTHON, "tools/gen_client_sdk.py", "--check"),
        ),
        CommandSpec(
            "python_sdk_contract",
            (
                PYTHON,
                "-m",
                "pytest",
                "tests/test_client_sdk_generator.py",
                "tests/test_client_sdk_contract.py",
                "-v",
                "--tb=short",
            ),
        ),
        CommandSpec(
            "typescript_sdk_reproducibility",
            (PYTHON, "tools/gen_typescript_sdk.py", "--check"),
        ),
        CommandSpec(
            "typescript_sdk_contract",
            (
                PYTHON,
                "-m",
                "pytest",
                "tests/test_typescript_sdk_generator.py",
                "-v",
                "--tb=short",
            ),
        ),
    ),
    "server-contract": (
        CommandSpec(
            "api_surface",
            (
                PYTHON,
                "-m",
                "pytest",
                "tests/test_server",
                "tests/test_hf_space_smoke.py",
                "-v",
                "--tb=short",
            ),
        ),
    ),
    "provider-runtime": (
        CommandSpec(
            "imports_and_browser_declarations",
            (PYTHON, "-c", PROVIDER_RUNTIME_CODE),
        ),
    ),
}
PROFILE_CHOICES = tuple(sorted(PROFILE_COMMANDS))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic SouWen CI profiles.")
    parser.add_argument(
        "--profile",
        action="append",
        choices=PROFILE_CHOICES,
        help="Profile to run. Repeat this option to run multiple profiles in order.",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-command timeout in seconds.",
    )
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--markdown-report", type=Path, default=None)
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available profiles and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_profiles:
        for profile in PROFILE_CHOICES:
            print(profile)
        return 0
    if not args.profile:
        parser.error("at least one --profile is required unless --list-profiles is used")

    recorder = run_profiles(args.profile, timeout=args.timeout)
    try:
        recorder.write_reports(json_report=args.json_report, markdown_report=args.markdown_report)
    except Exception as exc:  # noqa: BLE001 - report write failures have a fixed exit code.
        print(f"failed to write CI profile reports: {exc}", file=sys.stderr)
        return 2
    _print_summary(recorder)
    return recorder.exit_code()


def run_profiles(profiles: Sequence[str], *, timeout: float) -> ResultRecorder:
    recorder = ResultRecorder(
        script="ci_profile_runner",
        mode=",".join(profiles),
        environment={"profiles": list(profiles)},
    )
    for profile in profiles:
        for command in PROFILE_COMMANDS[profile]:
            _run_command(recorder, profile, command, timeout=timeout)
    return recorder


def _run_command(
    recorder: ResultRecorder,
    profile: str,
    spec: CommandSpec,
    *,
    timeout: float,
) -> None:
    start = time.perf_counter()
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.update(dict(spec.env))
    _ensure_source_pythonpath(env)
    command_text = shlex.join(spec.command)
    try:
        completed = _run_subprocess(
            spec.command,
            check=False,
            capture_output=True,
            env=env,
            text=True,
            timeout=timeout,
        )
        duration = time.perf_counter() - start
        details = {
            "command": command_text,
            "returncode": completed.returncode,
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        }
        if completed.returncode == 0:
            outcome = Outcome.PASS
            message = "ok"
        else:
            outcome = Outcome.FAIL if spec.required else Outcome.WARN
            message = f"exit code {completed.returncode}"
        recorder.record(
            f"{profile}/{spec.name}",
            outcome,
            required=spec.required,
            duration_seconds=duration,
            message=message,
            details=details,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - start
        recorder.record(
            f"{profile}/{spec.name}",
            Outcome.FAIL if spec.required else Outcome.WARN,
            required=spec.required,
            duration_seconds=duration,
            message=f"timeout after {timeout:.1f}s",
            details={
                "command": command_text,
                "timeout": timeout,
                "stdout_tail": _tail(exc.stdout),
                "stderr_tail": _tail(exc.stderr),
            },
        )
    except OSError as exc:
        duration = time.perf_counter() - start
        recorder.record(
            f"{profile}/{spec.name}",
            Outcome.FAIL if spec.required else Outcome.WARN,
            required=spec.required,
            duration_seconds=duration,
            message=str(exc),
            details={
                "command": command_text,
                "exception_type": type(exc).__name__,
            },
        )


def _ensure_source_pythonpath(env: dict[str, str]) -> None:
    """Keep profile subprocesses bound to the checked-out source tree."""

    source_root = str(SOURCE_ROOT)
    candidates = [source_root]
    existing = env.get("PYTHONPATH")
    if existing:
        candidates.extend(existing.split(os.pathsep))

    seen: set[str] = set()
    parts: list[str] = []
    for path in candidates:
        if path and path not in seen:
            seen.add(path)
            parts.append(path)
    env["PYTHONPATH"] = os.pathsep.join(parts)


def _tail(value: str | bytes | None, *, limit: int = OUTPUT_TAIL_CHARS) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if len(value) <= limit:
        return value
    return value[-limit:]


def _run_subprocess(command: tuple[str, ...], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, **kwargs)


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def _print_summary(recorder: ResultRecorder) -> None:
    print(f"ci_profile_runner overall={recorder.overall.value}")
    for check in recorder.checks:
        print(f"{check.outcome.value:4} {check.name} {check.message}")


if __name__ == "__main__":
    raise SystemExit(main())
