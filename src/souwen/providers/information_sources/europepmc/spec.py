"""Reviewed bridge declaration for the Europe PMC search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

EUROPEPMC_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="europepmc",
    adapter_id="europepmc-search",
    review_status="bridge_exception",
    bridge_reason="legacy result URLs have reviewed PMC, MED, and source-specific branches",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="www.ebi.ac.uk",
        base_path="/europepmc/webservices/rest",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled",),
)
