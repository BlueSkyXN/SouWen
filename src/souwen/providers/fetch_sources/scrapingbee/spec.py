"""Reviewed bridge declaration for ScrapingBee Fetch."""

from souwen.platform.provider_spec import ClientFetchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SCRAPINGBEE_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="scrapingbee",
    adapter_id="scrapingbee-fetch",
    adapter_reason="ScrapingBee rendering and local HTML extraction remain in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        host="app.scrapingbee.com",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/api/v1/"),),
    ),
    auth=AuthDeclaration(placement="query", reference="SCRAPINGBEE_API_KEY", field_name="api_key"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["SCRAPINGBEE_FETCH_PROFILE"]
