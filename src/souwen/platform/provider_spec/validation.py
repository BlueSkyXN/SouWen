"""Static agreement checks between typed Provider specs and package manifests."""

from __future__ import annotations

from souwen.platform.manifest_registry import ProviderManifest
from souwen.platform.provider_spec.models import ProviderSpec


def validate_spec_manifest(
    spec: ProviderSpec,
    manifest: ProviderManifest,
) -> ProviderSpec:
    """Fail closed when executable spec and governance manifest disagree."""
    if spec.provider_id != manifest.id:
        raise ValueError("provider spec identity does not match manifest")
    adapters = {adapter.id: adapter for adapter in manifest.adapters}
    declaration = adapters.get(spec.adapter_id)
    if declaration is None or declaration.capability != spec.capability:
        raise ValueError("provider spec adapter does not match manifest")
    spec_hosts = getattr(spec, "hosts", (spec.host,))
    if set(spec_hosts) != set(manifest.network.egress_hosts):
        raise ValueError("provider spec hosts do not match manifest egress hosts")
    if set(spec.configuration_keys) != set(manifest.configuration.non_secret_keys):
        raise ValueError("provider spec configuration does not match manifest")
    required_references = set(manifest.secrets.references)
    optional_references = set(manifest.secrets.optional_references)
    spec_required = {
        reference for reference, required in spec.auth_reference_requirements if required
    }
    spec_optional = {
        reference for reference, required in spec.auth_reference_requirements if not required
    }
    if spec_required != required_references or spec_optional != optional_references:
        raise ValueError("provider spec secret reference is not declared by manifest")
    return spec


__all__ = ["validate_spec_manifest"]
