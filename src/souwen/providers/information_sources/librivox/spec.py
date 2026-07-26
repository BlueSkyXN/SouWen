"""Reviewed search bridge declaration for LibriVox."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

LIBRIVOX_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="librivox",
    adapter_id="librivox-search",
    domain="book",
    adapter_reason="audiobook catalog normalization remains in the existing client",
    transport=ClientTransportDeclaration(
        host="librivox.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/api/feed/audiobooks/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["LIBRIVOX_PROVIDER_SPEC"]
