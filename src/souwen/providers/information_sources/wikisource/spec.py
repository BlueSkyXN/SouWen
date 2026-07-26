"""Reviewed search bridge declaration for fixed Wikisource hosts."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

WIKISOURCE_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="wikisource",
    adapter_id="wikisource-search",
    domain="book",
    bridge_reason="fixed language allowlist and page normalization remain in the legacy client",
    transport=LegacyTransportDeclaration(
        host="zh.wikisource.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/w/api.php"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["WIKISOURCE_PROVIDER_SPEC"]
