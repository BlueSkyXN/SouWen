"""Reviewed search bridge declaration for OAPEN."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

OAPEN_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="oapen",
    adapter_id="oapen-search",
    domain="book",
    bridge_reason="bounded OAI-PMH harvest filtering remains in the legacy client",
    transport=LegacyTransportDeclaration(
        host="library.oapen.org",
        protocol="xml",
        operations=(HttpOperation(method="GET", endpoint="/oai/request"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["OAPEN_PROVIDER_SPEC"]
