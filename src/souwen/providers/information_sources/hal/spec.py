"""Reviewed bridge declaration for the HAL Solr search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

HAL_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="hal",
    adapter_id="hal-search",
    review_status="reviewed_adapter",
    adapter_reason="existing HAL URLs use more than one reviewed record host and array normalization",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="api.archives-ouvertes.fr",
        base_path="/",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/"),),
    ),
    configuration_keys=("enabled",),
)
