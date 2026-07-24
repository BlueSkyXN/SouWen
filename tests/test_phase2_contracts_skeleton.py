"""Phase 2 language-neutral contracts boundary checks."""

from __future__ import annotations

from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = REPOSITORY_ROOT / "contracts"
CONTRACT_AREAS = (
    "openapi",
    "schemas",
    "errors",
    "provider",
    "security",
    "fixtures",
    "conformance",
)


@pytest.mark.parametrize("area", CONTRACT_AREAS)
def test_contract_area_has_language_neutral_ownership_card(area: str) -> None:
    readme = CONTRACTS_ROOT / area / "README.md"

    text = readme.read_text(encoding="utf-8")
    assert "Owner:" in text
    assert "Language-neutral" in text


def test_contracts_boundary_is_not_a_python_package() -> None:
    assert not (CONTRACTS_ROOT / "__init__.py").exists()
    assert list(CONTRACTS_ROOT.rglob("*.py")) == []


def test_contracts_skeleton_does_not_claim_target_artifacts() -> None:
    root_readme = (CONTRACTS_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Phase 2A creates only the directory skeleton" in root_readme
    assert "No target OpenAPI document" in root_readme
    assert "Target artifacts remain gated" in root_readme
