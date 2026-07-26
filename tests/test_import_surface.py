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
    from souwen.local_catalog import LocalCatalog
    from souwen.registry.meta import get_all_sources
    from souwen.search import search, search_all, search_by_capability, search_domain
    from souwen.web.fetch import fetch_content
    from souwen.web.wayback import WaybackClient
    from souwen import AsyncSouWenClient, SouWenClient

    assert callable(search)
    assert callable(search_all)
    assert callable(search_by_capability)
    assert callable(search_domain)
    assert callable(fetch_content)
    assert callable(get_all_sources)
    assert SouWenHttpClient.__name__ == "SouWenHttpClient"
    assert BaseScraper.__name__ == "BaseScraper"
    assert WaybackClient.__name__ == "WaybackClient"
    assert LocalCatalog.__name__ == "LocalCatalog"
    assert SouWenClient.__name__ == "SouWenClient"
    assert AsyncSouWenClient.__name__ == "AsyncSouWenClient"


def test_import_registry_does_not_scan_entry_points():
    """`import souwen.registry` must not execute entry-point discovery."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
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


def test_import_registry_keeps_concrete_web_providers_lazy():
    """Registry catalog initialization must not import concrete provider runtimes."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    code = """
import sys

from souwen.registry import all_adapters

assert all_adapters()
for name in (
    "souwen.web.builtin",
    "souwen.web.duckduckgo",
    "souwen.web.tavily",
    "trafilatura",
):
    assert name not in sys.modules, name
print("registry providers remain lazy")
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


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
