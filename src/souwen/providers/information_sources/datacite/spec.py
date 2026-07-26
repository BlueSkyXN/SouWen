"""Reviewed bridge declaration for DataCite's normalized metadata search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


DATACITE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="datacite",
    adapter_id="datacite-search",
    domain="research_output",
    adapter_reason=(
        "DataCite's typed research-output projection retains metadata beyond the canonical Search DTO"
    ),
    transport=ClientTransportDeclaration(
        scheme="https",
        host="api.datacite.org",
        base_path="/",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/dois"),),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["DATACITE_PROVIDER_SPEC"]
