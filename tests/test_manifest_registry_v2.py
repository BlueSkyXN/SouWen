"""Deterministic static conformance for the Provider v2 manifest registry."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from souwen.platform.manifest_registry.models import ProviderManifest
from souwen.platform.manifest_registry.registry import ManifestRegistry


_FIXTURE = Path(__file__).parent / "contracts" / "fixtures" / "target_provider_manifest_v2.json"


def _manifest() -> dict[str, object]:
    return copy.deepcopy(json.loads(_FIXTURE.read_text(encoding="utf-8"))["manifest"])


def test_target_fixture_is_a_valid_static_manifest_declaration() -> None:
    registry = ManifestRegistry()

    result = registry.register(_manifest())

    assert result.accepted is True
    assert result.manifest is not None
    assert registry.package("fixture-provider-package") == result.manifest
    resolved = registry.adapter("fixture-search")
    assert resolved is not None
    assert resolved[0].id == "fixture-provider-package"
    assert resolved[1].capability == "search"


def test_manifest_accepts_stable_underscore_adapter_ids_and_pep440_release_candidates() -> None:
    declaration = _manifest()
    declaration["id"] = "uniapi_provider_package"
    declaration["version"] = "2.0.0rc2"
    declaration["adapters"][0]["id"] = "uniapi_ark_annotations_deepseek_v3_2_251201"

    registry = ManifestRegistry()
    result = registry.register(declaration)

    assert result.accepted is True
    assert registry.package("uniapi_provider_package") is not None
    assert registry.adapter("uniapi_ark_annotations_deepseek_v3_2_251201") is not None


def test_manifest_distinguishes_required_and_optional_secret_references() -> None:
    declaration = _manifest()
    declaration["secrets"] = {
        "references": ["FIXTURE_PROVIDER_API_KEY"],
        "optional_references": ["FIXTURE_OPTIONAL_TOKEN"],
    }

    manifest = ProviderManifest.model_validate(declaration)

    assert manifest.secrets.references == ("FIXTURE_PROVIDER_API_KEY",)
    assert manifest.secrets.optional_references == ("FIXTURE_OPTIONAL_TOKEN",)
    assert manifest.secrets.all_references == (
        "FIXTURE_PROVIDER_API_KEY",
        "FIXTURE_OPTIONAL_TOKEN",
    )

    declaration["secrets"]["optional_references"] = ["FIXTURE_PROVIDER_API_KEY"]
    with pytest.raises(ValidationError):
        ProviderManifest.model_validate(declaration)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda declaration: declaration.pop("id"),
        lambda declaration: declaration.update(unexpected="value"),
        lambda declaration: declaration.update(capabilities=[]),
        lambda declaration: declaration["secrets"].update(values=["not-allowed"]),
        lambda declaration: declaration["secrets"].update(references=["https://secret.example"]),
        lambda declaration: declaration["configuration"].update(
            non_secret_keys=["enabled", "api_key"]
        ),
        lambda declaration: declaration["compatibility"].update(contract_versions=[]),
    ],
)
def test_manifest_model_rejects_missing_extra_secret_or_incompatible_declarations(mutate) -> None:
    declaration = _manifest()

    mutate(declaration)

    with pytest.raises(ValidationError):
        ProviderManifest.model_validate(declaration)


def test_registry_quarantines_only_new_duplicate_package_without_mutating_healthy_package() -> None:
    registry = ManifestRegistry()
    healthy = registry.register(_manifest())
    duplicate = _manifest()
    duplicate["version"] = "2.1.0"

    result = registry.register(duplicate)

    assert healthy.accepted is True
    assert result.accepted is False
    assert result.diagnostic is not None
    assert result.diagnostic.reason_code == "duplicate_package"
    assert registry.package("fixture-provider-package") == healthy.manifest
    assert len(registry.packages) == 1


def test_registry_transactionally_quarantines_new_package_with_duplicate_adapter() -> None:
    registry = ManifestRegistry()
    first = registry.register(_manifest())
    conflicting = _manifest()
    conflicting["id"] = "second-provider-package"
    conflicting["adapters"][0]["export"] = "SecondSearchProvider"

    result = registry.register(conflicting)

    assert first.accepted is True
    assert result.accepted is False
    assert result.diagnostic is not None
    assert result.diagnostic.reason_code == "duplicate_adapter"
    assert registry.package("second-provider-package") is None
    assert registry.adapter("fixture-search") is not None
    assert len(registry.packages) == 1


def test_discovery_keeps_valid_packages_when_another_declaration_is_invalid() -> None:
    invalid = _manifest()
    invalid["id"] = "not-a-secret"
    invalid["secrets"]["references"] = ["literal-secret-value"]
    healthy = _manifest()
    healthy["id"] = "healthy-provider-package"
    healthy["adapters"][0]["id"] = "healthy-search"
    healthy["adapters"][0]["export"] = "HealthySearchProvider"

    registry = ManifestRegistry()
    results = registry.discover((invalid, healthy))

    assert [result.accepted for result in results] == [False, True]
    assert registry.package("healthy-provider-package") is not None
    diagnostic = registry.diagnostics[0]
    assert diagnostic.reason_code == "manifest_invalid"
    assert "literal-secret-value" not in repr(diagnostic)
