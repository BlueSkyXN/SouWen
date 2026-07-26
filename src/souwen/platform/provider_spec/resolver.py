"""Small, value-free resolver boundary for Provider specification factories."""

from __future__ import annotations

from collections.abc import Mapping

from souwen.platform.provider_spec.models import ProviderSpec


def resolve_provider_inputs(
    spec: ProviderSpec,
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
) -> tuple[dict[str, object], dict[str, str]]:
    """Select only spec-declared keys and fail closed for a missing secret reference."""

    unknown = set(configuration).difference(spec.configuration_keys)
    if unknown:
        raise ValueError("unknown provider configuration")
    resolved_config = {
        key: configuration[key] for key in spec.configuration_keys if key in configuration
    }
    if spec.auth_reference is None:
        return resolved_config, {}
    value = secrets.get(spec.auth_reference)
    if value is None and not spec.auth.required:
        return resolved_config, {}
    if not isinstance(value, str) or not value.strip():
        raise ValueError("provider secret is unavailable")
    return resolved_config, {spec.auth_reference: value.strip()}
