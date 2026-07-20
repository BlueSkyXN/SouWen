from __future__ import annotations

import re
from pathlib import Path

from souwen.editions import FULL_FETCH_EXTRAS, fetch_provider_min_edition, source_min_edition
from souwen.feature_matrix import OPTIONAL_EXTRA_MODULES
from souwen.registry import all_adapters, fetch_providers


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _optional_dependencies() -> dict[str, list[str]]:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(
        r"^\[project\.optional-dependencies\]\n(?P<body>.*?)(?=^\[)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "missing [project.optional-dependencies]"

    extras: dict[str, list[str]] = {}
    for extra_match in re.finditer(
        r"^(?P<name>[A-Za-z0-9_.-]+) = \[(?P<body>.*?)\]\n",
        match.group("body"),
        flags=re.MULTILINE | re.DOTALL,
    ):
        extras[extra_match.group("name")] = re.findall(r'"([^"]+)"', extra_match.group("body"))
    return extras


def _used_registry_extras() -> set[str]:
    adapters = [*all_adapters().values(), *fetch_providers()]
    return {
        adapter.resolved_package_extra for adapter in adapters if adapter.resolved_package_extra
    }


def test_registry_package_extras_exist_in_pyproject() -> None:
    """Every registry package_extra must map to a declared optional dependency."""

    extras = _optional_dependencies()

    assert _used_registry_extras() <= set(extras)


def test_registry_package_extras_have_feature_matrix_probe_modules() -> None:
    """Every built-in package_extra should have an importability probe mapping."""

    assert _used_registry_extras() <= set(OPTIONAL_EXTRA_MODULES)


def test_heavy_fetch_extras_require_full_for_sources_and_fetch_providers() -> None:
    """Heavy local runtime extras should not be exposed as basic/pro sources."""

    heavy_sources = [
        adapter
        for adapter in all_adapters().values()
        if adapter.resolved_package_extra in FULL_FETCH_EXTRAS
    ]
    heavy_fetch_providers = [
        adapter
        for adapter in fetch_providers()
        if adapter.resolved_package_extra in FULL_FETCH_EXTRAS
    ]

    assert {adapter.name for adapter in heavy_sources} >= {
        "arxiv_fulltext",
        "crawl4ai",
        "scrapling",
        "newspaper",
        "readability",
    }
    assert all(source_min_edition(adapter) == "full" for adapter in heavy_sources)
    assert all(fetch_provider_min_edition(adapter) == "full" for adapter in heavy_fetch_providers)


def test_edition_extras_keep_conflicting_browser_stacks_separate() -> None:
    extras = _optional_dependencies()

    assert extras["edition-basic"] == ["souwen[tls,web,robots,mcp]"]
    assert extras["edition-pro"] == ["souwen[edition-basic,server,scraper]"]
    assert extras["edition-full"] == ["souwen[edition-pro,newspaper,readability,pdf,web2pdf]"]
    assert extras["edition-full-crawl4ai"] == ["souwen[edition-full,crawl4ai]"]
    assert extras["edition-full-scrapling"] == ["souwen[edition-full,scrapling]"]

    assert "crawl4ai" not in ",".join(extras["edition-full"])
    assert "scrapling" not in ",".join(extras["edition-full"])
