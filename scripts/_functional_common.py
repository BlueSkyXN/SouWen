"""Shared helpers for cloud functional checks."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import platform
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence


SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 30.0


class Outcome(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


class CheckSkipped(Exception):
    """Raised by a check when its runtime prerequisites are intentionally absent."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class CheckWarning(Exception):
    """Raised by a warn-only check when it should be recorded as WARN."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


@dataclass(slots=True)
class CheckResult:
    name: str
    outcome: Outcome
    required: bool
    duration_seconds: float
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "outcome": self.outcome.value,
            "required": self.required,
            "duration_seconds": round(self.duration_seconds, 3),
            "message": self.message,
            "details": self.details,
        }


@dataclass(slots=True)
class CommonArgs:
    mode: str
    timeout: float
    json_report: Path | None
    markdown_report: Path | None


class ResultRecorder:
    def __init__(
        self,
        *,
        script: str,
        mode: str,
        environment: Mapping[str, Any] | None = None,
    ) -> None:
        self.script = script
        self.mode = mode
        self.started_at = datetime.now(timezone.utc)
        self._start_monotonic = time.perf_counter()
        self.environment = {
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
        if environment:
            self.environment.update(dict(environment))
        self.checks: list[CheckResult] = []

    @property
    def duration_seconds(self) -> float:
        return time.perf_counter() - self._start_monotonic

    @property
    def overall(self) -> Outcome:
        if any(item.required and item.outcome == Outcome.FAIL for item in self.checks):
            return Outcome.FAIL
        if self.checks and all(item.outcome == Outcome.SKIP for item in self.checks):
            return Outcome.SKIP
        if any(item.outcome == Outcome.WARN for item in self.checks):
            return Outcome.WARN
        return Outcome.PASS

    def exit_code(self) -> int:
        return 1 if self.overall == Outcome.FAIL else 0

    def record(
        self,
        name: str,
        outcome: Outcome,
        *,
        required: bool,
        duration_seconds: float = 0.0,
        message: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> CheckResult:
        result = CheckResult(
            name=name,
            outcome=outcome,
            required=required,
            duration_seconds=duration_seconds,
            message=message,
            details=dict(details or {}),
        )
        self.checks.append(result)
        return result

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "script": self.script,
            "mode": self.mode,
            "overall": self.overall.value,
            "started_at": self.started_at.isoformat().replace("+00:00", "Z"),
            "duration_seconds": round(self.duration_seconds, 3),
            "environment": self.environment,
            "checks": [item.to_json() for item in self.checks],
        }

    def render_markdown(self) -> str:
        title = self.script.replace("_", " ").title()
        lines = [
            f"# {title}",
            "",
            f"Overall: **{self.overall.value}**",
            "",
            "| Check | Required | Outcome | Duration | Message |",
            "|---|---:|---|---:|---|",
        ]
        for check in self.checks:
            required = "yes" if check.required else "no"
            duration = f"{check.duration_seconds:.3f}s"
            lines.append(
                "| {name} | {required} | {outcome} | {duration} | {message} |".format(
                    name=_markdown_cell(check.name),
                    required=required,
                    outcome=check.outcome.value,
                    duration=duration,
                    message=_markdown_cell(check.message),
                )
            )
        lines.extend(["", "## JSON Summary", "", "```json", json.dumps(self.to_json(), indent=2)])
        lines.extend(["```", ""])
        return "\n".join(lines)

    def write_reports(
        self,
        *,
        json_report: Path | None = None,
        markdown_report: Path | None = None,
    ) -> None:
        if json_report is not None:
            json_report.parent.mkdir(parents=True, exist_ok=True)
            json_report.write_text(
                json.dumps(self.to_json(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if markdown_report is not None:
            markdown_report.parent.mkdir(parents=True, exist_ok=True)
            markdown_report.write_text(self.render_markdown(), encoding="utf-8")


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    default_mode: str = "fixture",
    modes: Sequence[str] = ("fixture", "live", "offline"),
) -> None:
    parser.add_argument(
        "--mode",
        choices=tuple(modes),
        default=default_mode,
        help="Functional check mode.",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-check timeout in seconds.",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=None,
        help="Write the machine-readable report to this path.",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=None,
        help="Write the human-readable report to this path.",
    )


def parse_common_args(
    description: str,
    argv: Sequence[str] | None = None,
    *,
    default_mode: str = "fixture",
    modes: Sequence[str] = ("fixture", "live", "offline"),
) -> CommonArgs:
    parser = argparse.ArgumentParser(description=description)
    add_common_args(parser, default_mode=default_mode, modes=modes)
    namespace = parser.parse_args(argv)
    return CommonArgs(
        mode=namespace.mode,
        timeout=namespace.timeout,
        json_report=namespace.json_report,
        markdown_report=namespace.markdown_report,
    )


async def run_check(
    recorder: ResultRecorder,
    name: str,
    check: Callable[[], Any | Awaitable[Any]],
    *,
    required: bool = True,
    timeout: float | None = None,
) -> CheckResult:
    start = time.perf_counter()
    try:
        value = check()
        if inspect.isawaitable(value):
            if timeout is None:
                value = await value
            else:
                value = await asyncio.wait_for(value, timeout=timeout)
        message, details = _normalize_check_value(value)
        outcome = Outcome.PASS
    except CheckSkipped as exc:
        message = str(exc)
        details = exc.details
        outcome = Outcome.SKIP
    except CheckWarning as exc:
        message = str(exc)
        details = exc.details
        outcome = Outcome.WARN
    except Exception as exc:  # noqa: BLE001 - check failures must be captured in reports.
        message = str(exc) or exc.__class__.__name__
        details = {
            "exception_type": exc.__class__.__name__,
            "traceback": traceback.format_exc(),
        }
        outcome = Outcome.FAIL if required else Outcome.WARN
    duration = time.perf_counter() - start
    if timeout is not None and duration > timeout and outcome == Outcome.PASS:
        outcome = Outcome.WARN if not required else Outcome.FAIL
        details = dict(details)
        details["timeout_seconds"] = timeout
        message = f"check exceeded timeout: {duration:.3f}s > {timeout:.3f}s"
    return recorder.record(
        name,
        outcome,
        required=required,
        duration_seconds=duration,
        message=message,
        details=details,
    )


def _normalize_check_value(value: Any) -> tuple[str, dict[str, Any]]:
    if value is None:
        return "ok", {}
    if isinstance(value, str):
        return value, {}
    if isinstance(value, Mapping):
        return "ok", dict(value)
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], Mapping)
    ):
        return value[0], dict(value[1])
    return str(value), {}


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
