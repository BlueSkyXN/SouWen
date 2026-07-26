"""Reviewed search bridge declaration for Internet Archive."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

INTERNET_ARCHIVE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="internet_archive",
    adapter_id="internet_archive-search",
    domain="book",
    adapter_reason="texts query and conservative catalog normalization remain in the existing client",
    transport=ClientTransportDeclaration(
        host="archive.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/advancedsearch.php"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["INTERNET_ARCHIVE_PROVIDER_SPEC"]
