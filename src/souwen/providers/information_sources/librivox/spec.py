"""Reviewed search bridge declaration for LibriVox."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

LIBRIVOX_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="librivox",
    adapter_id="librivox-search",
    domain="book",
    bridge_reason="audiobook catalog normalization remains in the legacy client",
    transport=LegacyTransportDeclaration(
        host="librivox.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/api/feed/audiobooks/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["LIBRIVOX_PROVIDER_SPEC"]
