"""Reviewed bridge declaration for the bioRxiv local-filtering search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

BIORXIV_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="biorxiv",
    adapter_id="biorxiv-search",
    review_status="reviewed_adapter",
    adapter_reason="existing search scans date windows and locally filters paged collection results",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="api.biorxiv.org",
        base_path="/details",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/details"),),
    ),
    configuration_keys=("enabled",),
)
