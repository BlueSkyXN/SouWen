from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts._functional_common import CheckSkipped, CheckWarning
from scripts import plugin_functional_check as check


def test_distribution_version_returns_none_for_missing_distribution() -> None:
    assert check.distribution_version("__definitely_missing_souwen_plugin__") is None


def test_example_distribution_missing_is_skip_when_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: None)

    with pytest.raises(CheckSkipped):
        check.verify_example_distribution(require_installed=False)


def test_example_distribution_missing_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: None)

    with pytest.raises(AssertionError):
        check.verify_example_distribution(require_installed=True)


def test_example_distribution_passes_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: "1.2.3")

    message, details = check.verify_example_distribution(require_installed=True)

    assert "distribution is installed" in message
    assert details["distribution"] == check.EXAMPLE_DISTRIBUTION
    assert details["version"] == "1.2.3"


def test_optional_web2pdf_missing_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: None)

    with pytest.raises(CheckWarning):
        check.verify_optional_web2pdf(require_installed=False)


def test_optional_web2pdf_missing_fails_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "distribution_version", lambda _name: None)

    with pytest.raises(AssertionError):
        check.verify_optional_web2pdf(require_installed=True)


def test_optional_web2pdf_installed_requires_registry_and_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = check.OPTIONAL_WEB2PDF_PLUGIN
    handler = object()
    info = SimpleNamespace(
        name=plugin,
        status="loaded",
        source_adapters=[plugin],
        fetch_handlers=[plugin],
    )

    monkeypatch.setattr(check, "distribution_version", lambda _name: "1.2.3")
    monkeypatch.setattr("souwen.plugin.ensure_plugins_loaded", lambda: None)
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {plugin: object()})
    monkeypatch.setattr("souwen.registry.external_plugins", lambda: [plugin])
    monkeypatch.setattr("souwen.web.fetch.get_fetch_handlers", lambda: {plugin: handler})
    monkeypatch.setattr("souwen.web.fetch.get_fetch_handler_owners", lambda: {plugin: plugin})
    monkeypatch.setattr("souwen.plugin_manager.list_plugins", lambda: [info])

    message, details = check.verify_optional_web2pdf(require_installed=False)

    assert "installed and registered" in message
    assert details == {
        "distribution": check.OPTIONAL_WEB2PDF_DISTRIBUTION,
        "version": "1.2.3",
        "plugin": plugin,
        "loaded": True,
        "external": True,
        "fetch_handler": True,
        "handler_owner": plugin,
        "plugin_status": "loaded",
    }


def test_optional_web2pdf_installed_without_fetch_handler_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = check.OPTIONAL_WEB2PDF_PLUGIN
    info = SimpleNamespace(
        name=plugin,
        status="loaded",
        source_adapters=[plugin],
        fetch_handlers=[],
    )

    monkeypatch.setattr(check, "distribution_version", lambda _name: "1.2.3")
    monkeypatch.setattr("souwen.plugin.ensure_plugins_loaded", lambda: None)
    monkeypatch.setattr("souwen.plugin.get_loaded_plugins", lambda: {plugin: object()})
    monkeypatch.setattr("souwen.registry.external_plugins", lambda: [plugin])
    monkeypatch.setattr("souwen.web.fetch.get_fetch_handlers", lambda: {})
    monkeypatch.setattr("souwen.web.fetch.get_fetch_handler_owners", lambda: {})
    monkeypatch.setattr("souwen.plugin_manager.list_plugins", lambda: [info])

    with pytest.raises(AssertionError, match="fetch handler not registered"):
        check.verify_optional_web2pdf(require_installed=False)


@pytest.mark.asyncio
async def test_optional_web2pdf_runtime_runs_under_full_edition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from souwen.config import get_config
    from souwen.models import FetchResponse, FetchResult

    captured: dict[str, object] = {}

    async def fake_fetch_content(urls, providers, timeout, skip_ssrf_check):
        captured.update(
            {
                "edition": get_config().edition,
                "urls": list(urls),
                "providers": list(providers),
                "timeout": timeout,
                "skip_ssrf_check": skip_ssrf_check,
            }
        )
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url=urls[0],
                    final_url=urls[0],
                    source=check.OPTIONAL_WEB2PDF_PLUGIN,
                    content="# SuperWeb2PDF Capture",
                    title="SuperWeb2PDF",
                    raw={
                        "page_count": 1,
                        "backend": "playwright",
                        "file_size_bytes": 2048,
                    },
                )
            ],
            total=1,
            total_ok=1,
            total_failed=0,
            provider=check.OPTIONAL_WEB2PDF_PLUGIN,
        )

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    monkeypatch.setattr("souwen.web.fetch.fetch_content", fake_fetch_content)

    message, details = await check.verify_optional_web2pdf_runtime(
        "http://127.0.0.1:12345/fixture",
        timeout=12,
    )

    assert "runtime fixture passed" in message
    assert details["provider"] == check.OPTIONAL_WEB2PDF_PLUGIN
    assert details["page_count"] == 1
    assert details["file_size_bytes"] == 2048
    assert captured == {
        "edition": "full",
        "urls": ["http://127.0.0.1:12345/fixture"],
        "providers": [check.OPTIONAL_WEB2PDF_PLUGIN],
        "timeout": 12,
        "skip_ssrf_check": True,
    }


@pytest.mark.asyncio
async def test_example_fetch_runs_under_full_edition(monkeypatch: pytest.MonkeyPatch) -> None:
    from souwen.config import get_config
    from souwen.models import FetchResponse, FetchResult

    captured: dict[str, object] = {}

    async def fake_fetch_content(urls, providers, timeout, skip_ssrf_check):
        captured.update(
            {
                "edition": get_config().edition,
                "urls": list(urls),
                "providers": list(providers),
                "timeout": timeout,
                "skip_ssrf_check": skip_ssrf_check,
            }
        )
        return FetchResponse(
            urls=list(urls),
            results=[
                FetchResult(
                    url=urls[0],
                    final_url=urls[0],
                    source=check.EXAMPLE_PLUGIN,
                    content=f"plugin content for {urls[0]}",
                    title="Example plugin",
                )
            ],
            total=1,
            total_ok=1,
            total_failed=0,
            provider=check.EXAMPLE_PLUGIN,
        )

    monkeypatch.setenv("SOUWEN_EDITION", "basic")
    monkeypatch.setattr("souwen.web.fetch.fetch_content", fake_fetch_content)

    message, details = await check.verify_example_fetch()

    assert "example plugin fetch handler passed" in message
    assert details["provider"] == check.EXAMPLE_PLUGIN
    assert captured == {
        "edition": "full",
        "urls": ["https://example.com/plugin-functional"],
        "providers": [check.EXAMPLE_PLUGIN],
        "timeout": 10,
        "skip_ssrf_check": True,
    }


def test_offline_mode_writes_skip_report(tmp_path: Path) -> None:
    json_report = tmp_path / "plugin.json"
    markdown_report = tmp_path / "plugin.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/plugin_functional_check.py",
            "--mode",
            "offline",
            "--json-report",
            str(json_report),
            "--markdown-report",
            str(markdown_report),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "SKIP offline_mode" in completed.stdout
    data = json.loads(json_report.read_text(encoding="utf-8"))
    assert data["script"] == "plugin_functional_check"
    assert data["mode"] == "offline"
    assert data["overall"] == "SKIP"
    assert data["checks"][0]["name"] == "offline_mode"
    assert data["checks"][0]["outcome"] == "SKIP"
    assert "Overall: **SKIP**" in markdown_report.read_text(encoding="utf-8")
