"""Reviewed bridge declaration for the HAL Solr search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

HAL_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="hal",
    adapter_id="hal-search",
    review_status="bridge_exception",
    bridge_reason="legacy HAL URLs use more than one reviewed record host and array normalization",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="api.archives-ouvertes.fr",
        base_path="/",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/"),),
    ),
    configuration_keys=("enabled",),
)
