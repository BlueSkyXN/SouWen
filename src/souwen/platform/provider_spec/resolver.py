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
    resolved_secrets: dict[str, str] = {}
    for reference, required in spec.auth_reference_requirements:
        value = secrets.get(reference)
        if value is None and not required:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError("provider secret is unavailable")
        resolved_secrets[reference] = value.strip()
    return resolved_config, resolved_secrets
