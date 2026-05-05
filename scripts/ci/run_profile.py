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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._functional_common import Outcome, ResultRecorder  # noqa: E402


DEFAULT_TIMEOUT_SECONDS = 300.0
OUTPUT_TAIL_CHARS = 4000
PYTHON = sys.executable or "python"


FULL_IMPORT_CODE = "\n".join(
    [
        "from souwen.paper import (",
        "    OpenAlexClient, SemanticScholarClient, CrossrefClient,",
        "    ArxivClient, DblpClient, CoreClient, PubMedClient, UnpaywallClient,",
        ")",
        "from souwen.patent import (",
        "    PatentsViewClient, PqaiClient, EpoOpsClient, UsptoOdpClient,",
        "    TheLensClient, CnipaClient, PatSnapClient, GooglePatentsClient,",
        ")",
        "from souwen.web import (",
        "    DuckDuckGoClient, YahooClient, BraveClient, GoogleClient, BingClient,",
        "    SearXNGClient, TavilyClient, ExaClient, SerperClient, BraveApiClient,",
        "    SerpApiClient, FirecrawlClient, PerplexityClient, LinkupClient,",
        "    ScrapingDogClient, StartpageClient, BaiduClient, MojeekClient,",
        "    YandexClient, WhoogleClient, WebsurfxClient, GitHubClient,",
        "    StackOverflowClient, RedditClient, BilibiliClient, WikipediaClient,",
        "    YouTubeClient, ZhihuClient, WeiboClient, BuiltinFetcherClient,",
        "    JinaReaderClient, web_search, fetch_content,",
        ")",
        "from souwen.doctor import check_all",
        "from souwen.plugin import discover_entrypoint_plugins, load_plugins",
        "from souwen.web.fetch import register_fetch_handler, get_fetch_handlers",
        "from souwen.registry.views import external_plugins",
        "print('all source, doctor, plugin and fetch handler imports OK')",
    ]
)


PLUGIN_DISCOVERY_CODE = "\n".join(
    [
        "from souwen.plugin import load_plugins",
        "from souwen.registry.views import external_plugins",
        "load_plugins()",
        "plugins = external_plugins()",
        "assert 'example_echo' in plugins, plugins",
        "print('example_echo plugin discovered')",
    ]
)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    command: tuple[str, ...]
    required: bool = True
    env: tuple[tuple[str, str], ...] = ()


PROFILE_COMMANDS: Mapping[str, tuple[CommandSpec, ...]] = {
    "minimal": (
        CommandSpec("cli_help", (PYTHON, "cli.py", "--help")),
        CommandSpec("cli_version", (PYTHON, "cli.py", "--version")),
        CommandSpec("sources_list", (PYTHON, "cli.py", "sources")),
        CommandSpec("config_show", (PYTHON, "cli.py", "config", "show")),
        CommandSpec("config_backend", (PYTHON, "cli.py", "config", "backend")),
        CommandSpec("module_help", (PYTHON, "-m", "souwen", "--help")),
    ),
    "server": (
        CommandSpec(
            "api_surface_tests",
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
    "full": (CommandSpec("all_optional_imports", (PYTHON, "-c", FULL_IMPORT_CODE)),),
    "plugin": (
        CommandSpec(
            "plugin_contract_tests",
            (
                PYTHON,
                "-m",
                "pytest",
                "tests/test_plugin.py",
                "tests/test_fetch_handlers.py",
                "-v",
                "--tb=short",
            ),
        ),
        CommandSpec(
            "example_plugin_contract",
            (
                PYTHON,
                "-m",
                "pytest",
                "examples/minimal-plugin/tests",
                "-v",
                "--tb=short",
            ),
        ),
        CommandSpec(
            "example_plugin_discovery",
            (PYTHON, "-c", PLUGIN_DISCOVERY_CODE),
            env=(("SOUWEN_PLUGIN_AUTOLOAD", "1"),),
        ),
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic SouWen CI profiles.")
    parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(PROFILE_COMMANDS),
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
        for profile in sorted(PROFILE_COMMANDS):
            print(profile)
        return 0
    if not args.profile:
        parser.error("at least one --profile is required unless --list-profiles is used")

    recorder = run_profiles(args.profile, timeout=args.timeout)
    recorder.write_reports(json_report=args.json_report, markdown_report=args.markdown_report)
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
