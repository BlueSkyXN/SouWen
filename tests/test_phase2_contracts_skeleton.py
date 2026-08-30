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


def test_contracts_boundary_claims_only_the_frozen_target_openapi() -> None:
    root_readme = (CONTRACTS_ROOT / "README.md").read_text(encoding="utf-8")
    openapi_readme = (CONTRACTS_ROOT / "openapi" / "README.md").read_text(encoding="utf-8")

    assert "target-only OpenAPI document is frozen" in root_readme
    assert "souwen-openapi-2.0.0rc6.json" in openapi_readme
    assert "tools/gen_openapi.py --check" in openapi_readme
    assert "Other schemas" in root_readme
