from __future__ import annotations

from souwen.editions import fetch_provider_policy, source_policy
from souwen.feature_matrix import (
    EDITIONS,
    allowed_warp_modes,
    declared_fetch_provider_names,
    declared_llm_protocols,
    declared_source_names,
    edition_capabilities,
    fetch_provider_min_edition,
    source_min_edition,
)
from souwen.registry import all_adapters, fetch_providers


def test_feature_matrix_reuses_existing_edition_derivation() -> None:
    """feature_matrix should not maintain a second source/provider policy."""

    for adapter in all_adapters().values():
        assert source_min_edition(adapter) == source_policy(adapter, "full").min_edition

    for adapter in fetch_providers():
        assert (
            fetch_provider_min_edition(adapter)
            == fetch_provider_policy(adapter, "full").min_edition
        )


def test_declared_source_names_are_derived_from_registry_policy() -> None:
    for edition in EDITIONS:
        expected = tuple(
            sorted(
                adapter.name
                for adapter in all_adapters().values()
                if source_policy(adapter, edition).available
            )
        )

        assert declared_source_names(edition) == expected


def test_declared_fetch_provider_names_are_derived_from_registry_policy() -> None:
    for edition in EDITIONS:
        expected = tuple(
            sorted(
                adapter.name
                for adapter in fetch_providers()
                if fetch_provider_policy(adapter, edition).available
            )
        )

        assert declared_fetch_provider_names(edition) == expected


def test_cross_cutting_declarations_follow_current_three_tier_policy() -> None:
    assert allowed_warp_modes("basic") == ("auto", "wireproxy", "external")
    assert allowed_warp_modes("pro") == (
        "auto",
        "wireproxy",
        "kernel",
        "usque",
        "warp-cli",
        "external",
    )
    assert allowed_warp_modes("full") == allowed_warp_modes("pro")

    assert declared_llm_protocols("basic") == ()
    assert declared_llm_protocols("pro") == (
        "openai_chat",
        "openai_responses",
        "anthropic_messages",
    )
    assert declared_llm_protocols("full") == declared_llm_protocols("pro")


def test_edition_capabilities_preserves_whoami_payload_shape(monkeypatch) -> None:
    monkeypatch.setattr("souwen.feature_matrix.plugin_preinstalled", lambda edition: False)

    assert edition_capabilities("basic") == {
        "llm": False,
        "warp_modes": ["auto", "wireproxy", "external"],
        "fetch_providers": ["builtin", "mcp", "site_crawler"],
        "plugin_preinstalled": False,
    }
