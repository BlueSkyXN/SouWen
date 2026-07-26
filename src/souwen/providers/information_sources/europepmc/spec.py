"""Reviewed bridge declaration for the Europe PMC search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

EUROPEPMC_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="europepmc",
    adapter_id="europepmc-search",
    review_status="reviewed_adapter",
    adapter_reason="existing result URLs have reviewed PMC, MED, and source-specific branches",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="www.ebi.ac.uk",
        base_path="/europepmc/webservices/rest",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled",),
)
