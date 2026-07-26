"""Reviewed bridge declaration for the legacy IACR HTML search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


IACR_BRIDGE_SPEC = LegacySearchProviderSpec(
    provider_id="iacr",
    adapter_id="iacr-search",
    bridge_reason="HTML selector parsing remains in the legacy IACR scraper bridge",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="eprint.iacr.org",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["IACR_BRIDGE_SPEC"]
