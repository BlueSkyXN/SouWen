"""Runtime availability checks derived from registry and configuration facts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from souwen.feature_matrix import REQUIRED_RUNTIME_EXTRAS, probe_optional_runtime

if TYPE_CHECKING:
    from souwen.config.models import SouWenConfig
    from souwen.registry.adapter import SourceAdapter


class CapabilityUnavailableError(ValueError):
    """Raised when a registered capability cannot safely be scheduled."""


def source_availability_reason(adapter: SourceAdapter, config: SouWenConfig) -> str:
    """Return a value-free reason when an adapter is not schedulable locally."""

    if not config.is_source_enabled(adapter.name, default=adapter.runtime_default_enabled):
        return f"source {adapter.name!r} is disabled"

    from souwen.registry.meta import (
        has_required_credentials,
        missing_credential_fields,
        source_config_validation_reason,
    )

    meta = SimpleNamespace(
        auth_requirement=adapter.resolved_auth_requirement,
        config_field=adapter.config_field,
        credential_fields=adapter.resolved_credential_fields,
    )
    config_reason = source_config_validation_reason(config, adapter.name, meta)
    if config_reason:
        return f"source {adapter.name!r} has invalid configuration: {config_reason}"
    if not has_required_credentials(config, adapter.name, meta):
        missing = missing_credential_fields(config, adapter.name, meta)
        fields = ", ".join(missing) if missing else "required credentials"
        return f"source {adapter.name!r} is unavailable: missing configuration: {fields}"
    if adapter.resolved_package_extra in REQUIRED_RUNTIME_EXTRAS:
        runtime = probe_optional_runtime(adapter)
        if not runtime.available:
            return f"source {adapter.name!r} is unavailable: {runtime.reason}"
    return ""


def ensure_source_available(adapter: SourceAdapter, config: SouWenConfig) -> None:
    """Raise a stable error before dispatching an unavailable source."""

    reason = source_availability_reason(adapter, config)
    if reason:
        raise CapabilityUnavailableError(reason)


def ensure_fetch_provider_available(adapter: SourceAdapter, config: SouWenConfig) -> None:
    """Apply the same registry/config/runtime checks to a fetch provider."""

    ensure_source_available(adapter, config)
