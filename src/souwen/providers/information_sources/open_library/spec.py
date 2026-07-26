"""Reviewed search bridge declaration for Open Library."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

OPEN_LIBRARY_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="open_library",
    adapter_id="open_library-search",
    domain="book",
    adapter_reason="existing work-level catalog normalization remains in the existing client",
    transport=ClientTransportDeclaration(
        host="openlibrary.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search.json"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["OPEN_LIBRARY_PROVIDER_SPEC"]
