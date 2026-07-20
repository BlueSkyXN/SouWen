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
FULL_FETCH_PROVIDER_MODULES: Mapping[str, str] = {
    "arxiv_fulltext": "souwen.paper.arxiv_fulltext",
    "crawl4ai": "souwen.web.crawl4ai_fetcher",
    "newspaper": "souwen.web.newspaper_fetcher",
    "readability": "souwen.web.readability_fetcher",
    "scrapling": "souwen.web.scrapling_fetcher",
}
FULL_FETCH_PROVIDER_MODULES_LITERAL = repr(dict(FULL_FETCH_PROVIDER_MODULES))
FULL_CORE_FETCH_PROVIDERS = frozenset({"arxiv_fulltext", "newspaper", "readability"})
FULL_BROWSER_VARIANT_FETCH_PROVIDERS = frozenset({"crawl4ai", "scrapling"})
FULL_CORE_FETCH_PROVIDERS_LITERAL = repr(tuple(sorted(FULL_CORE_FETCH_PROVIDERS)))
FULL_BROWSER_VARIANT_FETCH_PROVIDERS_LITERAL = repr(
    tuple(sorted(FULL_BROWSER_VARIANT_FETCH_PROVIDERS))
)

BASIC_RUNTIME_CODE = "\n".join(
    [
        "import mcp",
        "from souwen.feature_matrix import declared_fetch_provider_names, probe_capabilities",
        "from souwen.integrations.mcp.server import HAS_MCP, create_server",
        "from souwen.web.mcp_client import MCPClient",
        "assert HAS_MCP is True",
        "assert MCPClient.__name__ == 'MCPClient'",
        "assert create_server() is not None",
        "assert declared_fetch_provider_names('basic') == ('builtin', 'mcp', 'site_crawler')",
        "probe = probe_capabilities('basic')",
        "assert probe['fetch_providers'].declared == ('builtin', 'mcp', 'site_crawler')",
        "assert probe['fetch_providers'].available == ('builtin', 'mcp', 'site_crawler')",
        "assert probe['mcp'].available is True",
        "print('basic MCP client, stdio server and fetch providers OK')",
    ]
)


FULL_IMPORT_CODE = "\n".join(
    [
        "import importlib",
        "from souwen.config import get_config",
        "assert get_config().edition == 'full', get_config().edition",
        "from souwen.feature_matrix import declared_fetch_provider_names, probe_capabilities",
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
        "from souwen.plugin import discover_entrypoint_plugins, ensure_plugins_loaded",
        "from souwen.web.fetch import register_fetch_handler, get_fetch_handlers",
        "from souwen.registry.views import external_plugins",
        f"full_fetch_provider_modules = {FULL_FETCH_PROVIDER_MODULES_LITERAL}",
        f"full_core_fetch_providers = set({FULL_CORE_FETCH_PROVIDERS_LITERAL})",
        f"browser_variant_fetch_providers = set({FULL_BROWSER_VARIANT_FETCH_PROVIDERS_LITERAL})",
        "for _provider, _module_name in full_fetch_provider_modules.items():",
        "    importlib.import_module(_module_name)",
        "declared_fetch = set(declared_fetch_provider_names('full'))",
        "missing_declared = set(full_fetch_provider_modules) - declared_fetch",
        "assert not missing_declared, sorted(missing_declared)",
        "probe = probe_capabilities('full')",
        "available_fetch = set(probe['fetch_providers'].available)",
        "missing_core_importable = full_core_fetch_providers - available_fetch",
        "assert not missing_core_importable, sorted(missing_core_importable)",
        "available_browser_variants = browser_variant_fetch_providers & available_fetch",
        "assert len(available_browser_variants) <= 1, sorted(available_browser_variants)",
        "assert probe['mcp'].declared is True, probe['mcp']",
        "print('full core import surface and browser variant declarations OK')",
    ]
)


PLUGIN_DISCOVERY_CODE = "\n".join(
    [
        "from souwen.plugin import ensure_plugins_loaded",
        "from souwen.registry.views import external_plugins",
        "ensure_plugins_loaded()",
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
    "basic-cli": (
        CommandSpec("cli_help", (PYTHON, "cli.py", "--help"), env=(("SOUWEN_EDITION", "basic"),)),
        CommandSpec(
            "cli_version",
            (PYTHON, "cli.py", "--version"),
            env=(("SOUWEN_EDITION", "basic"),),
        ),
        CommandSpec(
            "sources_list",
            (PYTHON, "cli.py", "sources"),
            env=(("SOUWEN_EDITION", "basic"),),
        ),
        CommandSpec(
            "config_show",
            (PYTHON, "cli.py", "config", "show"),
            env=(("SOUWEN_EDITION", "basic"),),
        ),
        CommandSpec(
            "config_backend",
            (PYTHON, "cli.py", "config", "backend"),
            env=(("SOUWEN_EDITION", "basic"),),
        ),
        CommandSpec(
            "module_help",
            (PYTHON, "-m", "souwen", "--help"),
            env=(("SOUWEN_EDITION", "basic"),),
        ),
        CommandSpec(
            "doctor_edition",
            (PYTHON, "cli.py", "doctor", "edition", "--json"),
            env=(("SOUWEN_EDITION", "basic"),),
        ),
        CommandSpec(
            "mcp_runtime",
            (PYTHON, "-c", BASIC_RUNTIME_CODE),
            env=(("SOUWEN_EDITION", "basic"),),
        ),
    ),
    "pro-cli": (
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
            env=(("SOUWEN_EDITION", "pro"),),
        ),
    ),
    "full-cli": (
        CommandSpec(
            "core_runtime_and_browser_declarations",
            (PYTHON, "-c", FULL_IMPORT_CODE),
            env=(("SOUWEN_EDITION", "full"),),
        ),
    ),
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
PROFILE_ALIASES: Mapping[str, str] = {
    "minimal": "basic-cli",
    "server": "pro-cli",
    "full": "full-cli",
}
PROFILE_CHOICES = tuple(sorted((*PROFILE_COMMANDS, *PROFILE_ALIASES)))


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
        canonical_profile = PROFILE_ALIASES.get(profile, profile)
        for command in PROFILE_COMMANDS[canonical_profile]:
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
