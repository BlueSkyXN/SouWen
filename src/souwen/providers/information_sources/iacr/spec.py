"""Reviewed bridge declaration for the existing IACR HTML search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


IACR_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="iacr",
    adapter_id="iacr-search",
    adapter_reason="HTML selector parsing remains in the existing IACR scraper bridge",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="eprint.iacr.org",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["IACR_BRIDGE_SPEC"]
