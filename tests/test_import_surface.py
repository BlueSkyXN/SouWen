"""v2 public import surface tests."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_new_public_import_surface():
    """V2 公开入口只暴露真实模块路径。"""
    from souwen.core.http_client import SouWenHttpClient
    from souwen.core.scraper.base import BaseScraper
    from souwen.registry.meta import get_all_sources
    from souwen.search import search, search_all, search_by_capability, search_domain
    from souwen.web.fetch import fetch_content
    from souwen.web.wayback import WaybackClient

    assert callable(search)
    assert callable(search_all)
    assert callable(search_by_capability)
    assert callable(search_domain)
    assert callable(fetch_content)
    assert callable(get_all_sources)
    assert SouWenHttpClient.__name__ == "SouWenHttpClient"
    assert BaseScraper.__name__ == "BaseScraper"
    assert WaybackClient.__name__ == "WaybackClient"


def test_import_registry_does_not_scan_plugin_entry_points():
    """`import souwen.registry` must not execute third-party plugin discovery."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["SOUWEN_PLUGIN_AUTOLOAD"] = "1"
    code = """
import importlib.metadata as metadata

calls = 0

def fake_entry_points():
    global calls
    calls += 1
    raise AssertionError("entry_points should not be called")

metadata.entry_points = fake_entry_points
import souwen.registry
assert calls == 0, calls
print("registry import ok")
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_cli_bootstrap_calls_explicit_plugin_loader(monkeypatch):
    from souwen.plugin import PluginLoadResult

    import souwen.cli as cli_mod

    cfg = object()
    calls = []
    monkeypatch.setattr("souwen.config.get_config", lambda: cfg)
    monkeypatch.setattr(
        "souwen.plugin.ensure_plugins_loaded",
        lambda config: (
            calls.append(config)
            or PluginLoadResult(loaded_plugins=(), loaded_adapters=(), skipped=(), errors=())
        ),
    )

    cli_mod._bootstrap_plugins()

    assert calls == [cfg]


def test_server_bootstrap_calls_explicit_plugin_loader(monkeypatch):
    pytest.importorskip("fastapi")
    from souwen.plugin import PluginLoadResult

    from souwen.server import app as app_mod

    cfg = object()
    calls = []
    monkeypatch.setattr(
        app_mod,
        "ensure_plugins_loaded",
        lambda config: (
            calls.append(config)
            or PluginLoadResult(loaded_plugins=(), loaded_adapters=(), skipped=(), errors=())
        ),
    )

    app_mod._bootstrap_plugins(cfg)

    assert calls == [cfg]


@pytest.mark.parametrize(
    "name",
    [
        "souwen.facade",
        "souwen.source_registry",
        "souwen.exceptions",
        "souwen.http_client",
        "souwen.rate_limiter",
        "souwen._parsing",
        "souwen.retry",
        "souwen.fingerprint",
        "souwen.session_cache",
        "souwen.scraper",
        "souwen.scraper.base",
        "souwen.fetch",
        "souwen.fetch.providers",
        "souwen.cn_tech",
        "souwen.social",
        "souwen.video",
        "souwen.developer",
        "souwen.knowledge",
        "souwen.office",
        "souwen.archive",
        "souwen.web.engines",
        "souwen.web.api",
        "souwen.web.self_hosted",
    ],
)
def test_removed_import_surface(name):
    """V1 兼容路径在 V2 中必须不可 import。"""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(name)
