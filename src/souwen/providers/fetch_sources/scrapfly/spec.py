"""Reviewed bridge declaration for Scrapfly Fetch."""

from souwen.platform.provider_spec import ClientFetchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SCRAPFLY_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="scrapfly",
    adapter_id="scrapfly-fetch",
    adapter_reason="Scrapfly rendering and extracted-content selection remain in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        host="api.scrapfly.io",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/scrape"),),
    ),
    auth=AuthDeclaration(placement="query", reference="SCRAPFLY_API_KEY", field_name="key"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["SCRAPFLY_FETCH_PROFILE"]
