"""Reviewed bridge declaration for the CORE work-search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

CORE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="core",
    adapter_id="core-search",
    adapter_reason="existing work records require DOI or CORE-record canonicalization",
    transport=ClientTransportDeclaration(
        host="api.core.ac.uk",
        base_path="/v3",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/works"),),
    ),
    auth=AuthDeclaration(placement="bearer", reference="CORE_API_KEY", field_name="Authorization"),
    configuration_keys=("enabled",),
)
