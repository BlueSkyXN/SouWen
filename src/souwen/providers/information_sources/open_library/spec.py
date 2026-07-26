"""Reviewed search bridge declaration for Open Library."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

OPEN_LIBRARY_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="open_library",
    adapter_id="open_library-search",
    domain="book",
    bridge_reason="legacy work-level catalog normalization remains in the existing client",
    transport=LegacyTransportDeclaration(
        host="openlibrary.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search.json"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["OPEN_LIBRARY_PROVIDER_SPEC"]
