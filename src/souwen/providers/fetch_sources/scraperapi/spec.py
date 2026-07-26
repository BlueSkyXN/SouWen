"""Reviewed bridge declaration for ScraperAPI Fetch."""

from souwen.platform.provider_spec import LegacyFetchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SCRAPERAPI_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="scraperapi",
    adapter_id="scraperapi-fetch",
    bridge_reason="ScraperAPI rendering and local HTML extraction remain in the legacy Fetch bridge",
    transport=LegacyTransportDeclaration(
        host="api.scraperapi.com",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/"),),
    ),
    auth=AuthDeclaration(placement="query", reference="SCRAPERAPI_API_KEY", field_name="api_key"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["SCRAPERAPI_FETCH_PROFILE"]
