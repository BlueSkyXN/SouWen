"""Reviewed bridge declaration for OpenAIRE research-product search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

OPENAIRE_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="openaire",
    adapter_id="openaire-search",
    bridge_reason="nested OpenAIRE results need DOI or reviewed portal identity projection",
    transport=LegacyTransportDeclaration(
        host="api.openaire.eu",
        base_path="/",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/researchProducts"),),
    ),
    auth=AuthDeclaration(
        placement="bearer", reference="OPENAIRE_API_KEY", field_name="Authorization", required=False
    ),
    configuration_keys=("enabled",),
)
