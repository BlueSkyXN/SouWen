"""Cloud-only plugin functional check.

This script intentionally lives outside pytest. It validates real plugin package
installation and entry point discovery in CI, while keeping deterministic plugin
contract tests in pytest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from importlib import metadata

try:
    from scripts._functional_common import (
        CheckSkipped,
        CheckWarning,
        Outcome,
        ResultRecorder,
        add_common_args,
        run_check,
    )
except ModuleNotFoundError:  # pragma: no cover - direct `python scripts/...` execution.
    from _functional_common import (
        CheckSkipped,
        CheckWarning,
        Outcome,
        ResultRecorder,
        add_common_args,
        run_check,
    )


EXAMPLE_DISTRIBUTION = "souwen-example-plugin"
EXAMPLE_PLUGIN = "example_echo"
OPTIONAL_WEB2PDF_DISTRIBUTION = "superweb2pdf"
OPTIONAL_WEB2PDF_PLUGIN = "superweb2pdf"


def distribution_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_example_distribution(*, require_installed: bool) -> tuple[str, dict[str, object]]:
    version = distribution_version(EXAMPLE_DISTRIBUTION)
    if version is None:
        if not require_installed:
            raise CheckSkipped(
                f"{EXAMPLE_DISTRIBUTION} is not installed; CI should install it explicitly"
            )
        raise AssertionError(f"{EXAMPLE_DISTRIBUTION} distribution is not installed")
    return (
        f"{EXAMPLE_DISTRIBUTION} distribution is installed",
        {"distribution": EXAMPLE_DISTRIBUTION, "version": version},
    )


def verify_example_contract() -> tuple[str, dict[str, object]]:
    from souwen.plugin import get_loaded_plugins
    from souwen.testing import assert_valid_plugin, validate_client_contract

    plugin = get_loaded_plugins().get(EXAMPLE_PLUGIN)
    require(plugin is not None, f"{EXAMPLE_PLUGIN} plugin object not loaded")

    assert_valid_plugin(plugin)
    issue_map: dict[str, list[str]] = {}
    for adapter in plugin.adapters:
        client_issues = validate_client_contract(adapter)
        if client_issues:
            issue_map[adapter.name] = client_issues
    require(not issue_map, str(issue_map))
    return (
        "example plugin contract check passed",
        {
            "plugin": EXAMPLE_PLUGIN,
            "adapters": [adapter.name for adapter in plugin.adapters],
            "methods": {adapter.name: sorted(adapter.methods) for adapter in plugin.adapters},
        },
    )


def verify_entry_point_registry() -> tuple[str, dict[str, object]]:
    from souwen.plugin import get_loaded_plugins
    from souwen.plugin_manager import list_plugins
    from souwen.registry import all_adapters, external_plugins
    from souwen.web.fetch import get_fetch_handler_owners, get_fetch_handlers

    external = set(external_plugins())
    adapters = all_adapters()
    handlers = get_fetch_handlers()
    handler_owners = get_fetch_handler_owners()
    loaded_plugins = get_loaded_plugins()
    plugin_infos = {item.name: item for item in list_plugins()}

    require(EXAMPLE_PLUGIN in external, f"{EXAMPLE_PLUGIN} not in external_plugins: {external}")
    require(EXAMPLE_PLUGIN in adapters, f"{EXAMPLE_PLUGIN} adapter not registered")
    require(EXAMPLE_PLUGIN in handlers, f"{EXAMPLE_PLUGIN} fetch handler not registered")
    require(
        handler_owners.get(EXAMPLE_PLUGIN) == EXAMPLE_PLUGIN,
        f"{EXAMPLE_PLUGIN} handler owner mismatch: {handler_owners.get(EXAMPLE_PLUGIN)!r}",
    )
    require(EXAMPLE_PLUGIN in loaded_plugins, f"{EXAMPLE_PLUGIN} plugin object not loaded")
    info = plugin_infos.get(EXAMPLE_PLUGIN)
    require(info is not None, f"{EXAMPLE_PLUGIN} missing from plugin manager list")
    require(info.status == "loaded", f"unexpected plugin status: {info.status}")
    require(EXAMPLE_PLUGIN in info.source_adapters, f"adapter missing from PluginInfo: {info}")
    require(EXAMPLE_PLUGIN in info.fetch_handlers, f"fetch handler missing from PluginInfo: {info}")

    return (
        "entry point plugin discovery and registry views passed",
        {
            "plugin": EXAMPLE_PLUGIN,
            "external_plugins": sorted(external),
            "handler_owner": handler_owners.get(EXAMPLE_PLUGIN),
            "plugin_status": info.status,
            "source": info.source,
        },
    )


async def verify_example_fetch() -> tuple[str, dict[str, object]]:
    from souwen.web.fetch import fetch_content

    url = "https://example.com/plugin-functional"
    response = await fetch_content(
        urls=[url],
        providers=[EXAMPLE_PLUGIN],
        timeout=10,
        skip_ssrf_check=True,
    )
    require(response.provider == EXAMPLE_PLUGIN, f"unexpected provider: {response.provider}")
    require(response.total == 1, f"unexpected total: {response.total}")
    require(response.total_ok == 1, f"unexpected total_ok: {response.total_ok}")
    result = response.results[0]
    require(result.error is None, f"unexpected error: {result.error}")
    require(result.source == EXAMPLE_PLUGIN, f"unexpected source: {result.source}")
    require(url in result.content, "expected URL not found in plugin content")
    return (
        f"example plugin fetch handler passed: {result.final_url}",
        {
            "url": url,
            "final_url": result.final_url,
            "provider": response.provider,
            "title": result.title,
        },
    )


def verify_optional_web2pdf(*, require_installed: bool) -> tuple[str, dict[str, object]]:
    version = distribution_version(OPTIONAL_WEB2PDF_DISTRIBUTION)
    if version is None:
        if require_installed:
            raise AssertionError(f"{OPTIONAL_WEB2PDF_DISTRIBUTION} distribution is not installed")
        raise CheckWarning(
            "optional superweb2pdf distribution is not installed",
            details={"distribution": OPTIONAL_WEB2PDF_DISTRIBUTION},
        )

    from souwen.plugin import get_loaded_plugins
    from souwen.registry import external_plugins

    external = set(external_plugins())
    loaded_plugins = get_loaded_plugins()
    require(
        OPTIONAL_WEB2PDF_PLUGIN in external or OPTIONAL_WEB2PDF_PLUGIN in loaded_plugins,
        f"{OPTIONAL_WEB2PDF_PLUGIN} installed but not loaded",
    )
    return (
        "optional superweb2pdf plugin is installed and visible",
        {
            "distribution": OPTIONAL_WEB2PDF_DISTRIBUTION,
            "version": version,
            "plugin": OPTIONAL_WEB2PDF_PLUGIN,
            "loaded": OPTIONAL_WEB2PDF_PLUGIN in loaded_plugins,
            "external": OPTIONAL_WEB2PDF_PLUGIN in external,
        },
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run cloud-only plugin functional checks.")
    add_common_args(parser, default_mode="fixture")
    parser.add_argument(
        "--require-installed",
        action="store_true",
        help="Treat missing minimal example plugin installation as FAIL instead of SKIP.",
    )
    parser.add_argument(
        "--require-web2pdf",
        action="store_true",
        help="Treat missing or unloaded optional superweb2pdf plugin as FAIL.",
    )
    args = parser.parse_args()
    recorder = ResultRecorder(script="plugin_functional_check", mode=args.mode)

    try:
        if args.mode == "offline":
            recorder.record(
                "offline_mode",
                outcome=Outcome.SKIP,
                required=False,
                message="offline mode requested; plugin functional checks skipped",
            )
        else:
            distribution_result = await run_check(
                recorder,
                "example_distribution",
                lambda: verify_example_distribution(require_installed=args.require_installed),
                required=args.require_installed,
                timeout=args.timeout,
            )
            if distribution_result.outcome != Outcome.PASS:
                recorder.record(
                    "example_entry_point",
                    outcome=Outcome.SKIP,
                    required=False,
                    message="example plugin distribution did not pass; entry point checks skipped",
                )
            else:
                await run_check(
                    recorder,
                    "example_entry_point",
                    verify_entry_point_registry,
                    required=True,
                    timeout=args.timeout,
                )
                await run_check(
                    recorder,
                    "example_fetch_handler",
                    verify_example_fetch,
                    required=True,
                    timeout=args.timeout,
                )
                await run_check(
                    recorder,
                    "example_contract",
                    verify_example_contract,
                    required=True,
                    timeout=args.timeout,
                )

            await run_check(
                recorder,
                "optional_web2pdf",
                lambda: verify_optional_web2pdf(require_installed=args.require_web2pdf),
                required=args.require_web2pdf,
                timeout=args.timeout,
            )
    finally:
        try:
            recorder.write_reports(
                json_report=args.json_report,
                markdown_report=args.markdown_report,
            )
        except Exception as exc:  # noqa: BLE001 - report write failures have a fixed exit code.
            print(f"failed to write functional check reports: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc

    for check in recorder.checks:
        print(
            "{outcome} {name}: {message}".format(
                outcome=check.outcome.value,
                name=check.name,
                message=check.message,
            )
        )
    raise SystemExit(recorder.exit_code())


if __name__ == "__main__":
    asyncio.run(main())
