"""Reviewed bridge declaration for ScrapingBee Fetch."""

from souwen.platform.provider_spec import LegacyFetchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SCRAPINGBEE_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="scrapingbee",
    adapter_id="scrapingbee-fetch",
    bridge_reason="ScrapingBee rendering and local HTML extraction remain in the legacy Fetch bridge",
    transport=LegacyTransportDeclaration(
        host="app.scrapingbee.com",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/api/v1/"),),
    ),
    auth=AuthDeclaration(placement="query", reference="SCRAPINGBEE_API_KEY", field_name="api_key"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["SCRAPINGBEE_FETCH_PROFILE"]
