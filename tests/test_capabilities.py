"""Deterministic dispatch-readiness checks for registry adapters."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from souwen.capabilities import (
    CapabilityUnavailableError,
    ensure_fetch_provider_available,
    ensure_source_available,
    source_availability_reason,
)
from souwen.config import SouWenConfig
from souwen.feature_matrix import RuntimeProbe
from souwen.registry.adapter import MethodSpec, SourceAdapter


def _adapter(**overrides) -> SourceAdapter:
    values = {
        "name": "capability_fixture",
        "domain": "web",
        "integration": "official_api",
        "description": "capability fixture",
        "config_field": "openalex_api_key",
        "client_loader": lambda: object,
        "methods": {"search": MethodSpec("search")},
        "auth_requirement": "required",
    }
    values.update(overrides)
    return SourceAdapter(**values)


def test_disabled_source_is_rejected_before_runtime_probe(monkeypatch) -> None:
    probe = Mock(return_value=RuntimeProbe(True))
    monkeypatch.setattr("souwen.capabilities.probe_optional_runtime", probe)
    config = SouWenConfig(sources={"capability_fixture": {"enabled": False}})

    with pytest.raises(CapabilityUnavailableError, match="is disabled"):
        ensure_source_available(_adapter(), config)

    probe.assert_not_called()


def test_missing_required_credentials_are_value_free() -> None:
    reason = source_availability_reason(_adapter(), SouWenConfig())

    assert reason == (
        "source 'capability_fixture' is unavailable: missing configuration: openalex_api_key"
    )


def test_invalid_configuration_is_rejected_before_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        "souwen.registry.meta.source_config_validation_reason",
        lambda *_args: "invalid source base_url: sources.capability_fixture.base_url",
    )
    reason = source_availability_reason(
        _adapter(),
        SouWenConfig(openalex_api_key="secret-canary"),
    )

    assert reason.endswith("invalid source base_url: sources.capability_fixture.base_url")
    assert "secret-canary" not in reason


def test_missing_required_runtime_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        "souwen.capabilities.probe_optional_runtime",
        lambda _adapter: RuntimeProbe(False, "missing modules: optional_sdk"),
    )
    config = SouWenConfig(openalex_api_key="secret-canary")

    with pytest.raises(CapabilityUnavailableError, match="missing modules: optional_sdk"):
        ensure_source_available(_adapter(package_extra="crawl4ai"), config)


def test_fallback_extra_is_not_a_hard_runtime_gate(monkeypatch) -> None:
    probe = Mock(return_value=RuntimeProbe(False, "missing modules: trafilatura"))
    monkeypatch.setattr("souwen.capabilities.probe_optional_runtime", probe)

    reason = source_availability_reason(
        _adapter(package_extra="web"),
        SouWenConfig(openalex_api_key="secret-canary"),
    )

    assert reason == ""
    probe.assert_not_called()


def test_ready_source_and_fetch_wrapper_pass(monkeypatch) -> None:
    probe = Mock(return_value=RuntimeProbe(True))
    monkeypatch.setattr("souwen.capabilities.probe_optional_runtime", probe)
    config = SouWenConfig(openalex_api_key="secret-canary")
    adapter = _adapter(package_extra="crawl4ai")

    assert source_availability_reason(adapter, config) == ""
    ensure_fetch_provider_available(adapter, config)

    assert probe.call_count == 2
