"""Reviewed search bridge declaration for Internet Archive."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

INTERNET_ARCHIVE_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="internet_archive",
    adapter_id="internet_archive-search",
    domain="book",
    bridge_reason="texts query and conservative catalog normalization remain in the legacy client",
    transport=LegacyTransportDeclaration(
        host="archive.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/advancedsearch.php"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["INTERNET_ARCHIVE_PROVIDER_SPEC"]
