"""Reviewed search bridge declaration for fixed Wikisource hosts."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

WIKISOURCE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="wikisource",
    adapter_id="wikisource-search",
    domain="book",
    adapter_reason="fixed language allowlist and page normalization remain in the existing client",
    transport=ClientTransportDeclaration(
        host="zh.wikisource.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/w/api.php"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["WIKISOURCE_PROVIDER_SPEC"]
