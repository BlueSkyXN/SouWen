from __future__ import annotations

import pytest

from souwen.editions import (
    EDITIONS,
    EDITION_RANK,
    EditionError,
    allowed_warp_modes,
    edition_allows,
    ensure_edition_allowed,
    fetch_provider_min_edition,
    fetch_provider_policy,
    ensure_warp_mode_allowed,
    llm_available,
    plugin_preinstalled,
    source_min_edition,
    source_policy,
    warp_mode_policy,
)
from souwen.registry import all_adapters, fetch_providers, get
from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.views import _reg_external


def _adapter(name: str) -> SourceAdapter:
    adapter = get(name)
    assert adapter is not None, f"missing registry adapter: {name}"
    return adapter


def test_edition_allows_monotonic_access() -> None:
    assert edition_allows("basic", "basic")
    assert not edition_allows("basic", "pro")
    assert not edition_allows("basic", "full")

    assert edition_allows("pro", "basic")
    assert edition_allows("pro", "pro")
    assert not edition_allows("pro", "full")

    assert edition_allows("full", "basic")
    assert edition_allows("full", "pro")
    assert edition_allows("full", "full")


def test_unknown_edition_is_rejected() -> None:
    with pytest.raises(ValueError, match="current must be one of"):
        edition_allows("enterprise", "basic")

    with pytest.raises(ValueError, match="required must be one of"):
        edition_allows("basic", "enterprise")


def test_ensure_edition_allowed_raises_stable_error() -> None:
    with pytest.raises(EditionError, match="LLM requires edition=pro, current edition=basic"):
        ensure_edition_allowed("LLM", current="basic", required="pro")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("arxiv", "basic"),
        ("duckduckgo", "basic"),
        ("bilibili", "basic"),
        ("wayback", "basic"),
        ("mcp", "basic"),
        ("openalex", "pro"),
        ("tavily", "pro"),
        ("searxng", "pro"),
        ("youtube", "pro"),
        ("crawl4ai", "full"),
        ("scrapling", "full"),
        ("newspaper", "full"),
        ("readability", "full"),
        ("arxiv_fulltext", "full"),
    ],
)
def test_source_min_edition_uses_registry_metadata(name: str, expected: str) -> None:
    assert source_min_edition(_adapter(name)) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("builtin", "basic"),
        ("site_crawler", "basic"),
        ("mcp", "basic"),
        ("jina_reader", "pro"),
        ("deepwiki", "pro"),
        ("wayback", "pro"),
        ("tavily", "pro"),
        ("firecrawl", "pro"),
        ("exa", "pro"),
        ("cloudflare", "pro"),
        ("metaso", "pro"),
        ("kimi_code", "pro"),
        ("crawl4ai", "full"),
        ("scrapling", "full"),
        ("newspaper", "full"),
        ("readability", "full"),
        ("arxiv_fulltext", "full"),
    ],
)
def test_fetch_provider_min_edition_uses_provider_rules(name: str, expected: str) -> None:
    assert fetch_provider_min_edition(_adapter(name)) == expected


def test_policy_metadata_reports_denied_reason_without_raising() -> None:
    policy = fetch_provider_policy(_adapter("crawl4ai"), "pro")

    assert policy.min_edition == "full"
    assert not policy.available
    assert policy.reason == "fetch provider 'crawl4ai' requires edition=full, current edition=pro"


def test_cross_feature_edition_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
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

    assert not llm_available("basic")
    assert llm_available("pro")
    assert llm_available("full")

    monkeypatch.setattr("souwen.editions._plugin_package_importable", lambda _: True)
    assert not plugin_preinstalled("basic")
    assert not plugin_preinstalled("pro")
    assert plugin_preinstalled("full")

    monkeypatch.setattr("souwen.editions._plugin_package_importable", lambda _: False)
    assert not plugin_preinstalled("full")


def test_warp_mode_policy_reports_denied_modes_without_masking_unknown() -> None:
    policy = warp_mode_policy("usque", "basic")

    assert policy.min_edition == "pro"
    assert not policy.available
    assert policy.reason == "WARP mode 'usque' requires edition=pro, current edition=basic"

    ensure_warp_mode_allowed("custom-mode", "basic")
    with pytest.raises(EditionError, match="WARP mode 'kernel' requires edition=pro"):
        ensure_warp_mode_allowed("kernel", "basic")


def test_registry_source_policies_are_valid_and_monotonic() -> None:
    for adapter in all_adapters().values():
        min_edition = source_min_edition(adapter)
        assert min_edition in EDITION_RANK

        seen_available = False
        for edition in EDITIONS:
            policy = source_policy(adapter, edition)
            assert policy.min_edition == min_edition
            assert policy.available is edition_allows(edition, min_edition)
            assert bool(policy.reason) is not policy.available
            if seen_available:
                assert policy.available
            seen_available = seen_available or policy.available


def test_registry_fetch_provider_policies_are_valid_and_monotonic() -> None:
    for adapter in fetch_providers():
        min_edition = fetch_provider_min_edition(adapter)
        assert min_edition in EDITION_RANK

        seen_available = False
        for edition in EDITIONS:
            policy = fetch_provider_policy(adapter, edition)
            assert policy.min_edition == min_edition
            assert policy.available is edition_allows(edition, min_edition)
            assert bool(policy.reason) is not policy.available
            if seen_available:
                assert policy.available
            seen_available = seen_available or policy.available


def test_external_plugin_adapter_requires_full(clean_registry) -> None:
    adapter = SourceAdapter(
        name="plugin_fetch",
        domain="fetch",
        integration="open_api",
        description="Test plugin fetch provider",
        config_field=None,
        client_loader=lambda: object,
        methods={"fetch": MethodSpec("fetch")},
    )

    assert _reg_external(adapter)
    assert source_min_edition(adapter) == "full"
    assert fetch_provider_min_edition(adapter) == "full"
