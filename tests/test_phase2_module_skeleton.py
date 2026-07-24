"""Phase 2 package-boundary skeleton checks."""

from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src" / "souwen"

SKELETON_PACKAGES = (
    "souwen.delivery",
    "souwen.delivery.api",
    "souwen.delivery.client_sdk",
    "souwen.modules",
    "souwen.modules.search",
    "souwen.modules.search.api",
    "souwen.modules.search.application",
    "souwen.modules.search.domain",
    "souwen.modules.search.infrastructure",
    "souwen.modules.llm_search",
    "souwen.modules.llm_search.api",
    "souwen.modules.llm_search.application",
    "souwen.modules.llm_search.domain",
    "souwen.modules.llm_search.infrastructure",
    "souwen.modules.fetch",
    "souwen.modules.fetch.api",
    "souwen.modules.fetch.application",
    "souwen.modules.fetch.domain",
    "souwen.modules.fetch.infrastructure",
    "souwen.platform",
    "souwen.platform.provider_manager",
    "souwen.platform.provider_spi",
    "souwen.platform.manifest_registry",
    "souwen.common_runtime",
    "souwen.common_runtime.transport",
    "souwen.common_runtime.resilience",
    "souwen.common_runtime.security",
    "souwen.common_runtime.configuration",
    "souwen.common_runtime.testing",
    "souwen.providers",
    "souwen.providers.information_sources",
    "souwen.providers.llm_sources",
    "souwen.providers.fetch_sources",
)


def _package_path(package_name: str) -> Path:
    return SOURCE_ROOT.joinpath(*package_name.split(".")[1:], "__init__.py")


@pytest.mark.parametrize("package_name", SKELETON_PACKAGES)
def test_phase2_packages_import_from_souwen_distribution(package_name: str) -> None:
    """Each boundary remains inside the existing ``souwen`` distribution root."""
    package = importlib.import_module(package_name)
    package_file = Path(package.__file__).resolve()

    assert package_file.is_relative_to(SOURCE_ROOT.resolve())
    assert package.__all__ == []


@pytest.mark.parametrize("package_name", SKELETON_PACKAGES)
def test_phase2_packages_declare_an_empty_internal_interface(package_name: str) -> None:
    """Skeletons state ownership/boundaries without adding an end-user API."""
    tree = ast.parse(_package_path(package_name).read_text(encoding="utf-8"))
    docstring = ast.get_docstring(tree)

    assert docstring is not None
    assert "Owner:" in docstring
    assert "Allowed dependencies:" in docstring
    assert any(
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "__all__"
        and isinstance(node.value, ast.List)
        and not node.value.elts
        for node in tree.body
    )


@pytest.mark.parametrize("package_name", SKELETON_PACKAGES)
def test_phase2_packages_have_no_legacy_or_optional_imports(package_name: str) -> None:
    """Skeletons must be inert until a later migration intentionally adds a dependency."""
    tree = ast.parse(_package_path(package_name).read_text(encoding="utf-8"))

    assert not any(isinstance(node, ast.Import | ast.ImportFrom) for node in ast.walk(tree))
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
        for node in ast.walk(tree)
    )


def test_phase2_package_imports_add_no_runtime_modules() -> None:
    """Package imports add only the requested skeleton packages after ``souwen`` is loaded."""
    script = f"""
import importlib
import json
import sys

import souwen

before = set(sys.modules)
for package_name in {SKELETON_PACKAGES!r}:
    importlib.import_module(package_name)
print(json.dumps(sorted(set(sys.modules) - before)))
"""
    environment = os.environ.copy()
    source_path = str(REPOSITORY_ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        path for path in (source_path, environment.get("PYTHONPATH")) if path
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    added_modules = set(json.loads(result.stdout))
    assert added_modules <= set(SKELETON_PACKAGES)
