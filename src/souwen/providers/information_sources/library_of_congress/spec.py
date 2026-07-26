"""Reviewed search bridge declaration for the Library of Congress."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

LIBRARY_OF_CONGRESS_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="library_of_congress",
    adapter_id="library_of_congress-search",
    domain="book",
    bridge_reason="LOC catalog resource and rights normalization remains in the legacy client",
    transport=LegacyTransportDeclaration(
        host="www.loc.gov",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/books/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["LIBRARY_OF_CONGRESS_PROVIDER_SPEC"]
