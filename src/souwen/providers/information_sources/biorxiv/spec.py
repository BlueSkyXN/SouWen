"""Reviewed bridge declaration for the bioRxiv local-filtering search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

BIORXIV_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="biorxiv",
    adapter_id="biorxiv-search",
    review_status="bridge_exception",
    bridge_reason="legacy search scans date windows and locally filters paged collection results",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="api.biorxiv.org",
        base_path="/details",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/details"),),
    ),
    configuration_keys=("enabled",),
)
