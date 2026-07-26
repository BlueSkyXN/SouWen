"""Static agreement checks between typed Provider specs and package manifests."""

from __future__ import annotations

from souwen.platform.manifest_registry import ProviderManifest
from souwen.platform.provider_spec.models import RestJsonProviderSpec


def validate_spec_manifest(
    spec: RestJsonProviderSpec,
    manifest: ProviderManifest,
) -> RestJsonProviderSpec:
    """Fail closed when executable spec and governance manifest disagree."""
    if spec.provider_id != manifest.id:
        raise ValueError("provider spec identity does not match manifest")
    adapters = {adapter.id: adapter for adapter in manifest.adapters}
    declaration = adapters.get(spec.adapter_id)
    if declaration is None or declaration.capability != spec.capability:
        raise ValueError("provider spec adapter does not match manifest")
    if spec.host not in manifest.network.egress_hosts:
        raise ValueError("provider spec host is not declared by manifest")
    if set(spec.configuration_keys) != set(manifest.configuration.non_secret_keys):
        raise ValueError("provider spec configuration does not match manifest")
    declared_references = set(manifest.secrets.references)
    spec_references = {spec.auth_reference} if spec.auth_reference is not None else set()
    if spec_references != declared_references:
        raise ValueError("provider spec secret reference is not declared by manifest")
    return spec


__all__ = ["validate_spec_manifest"]
