"""Reviewed bridge declaration for ScraperAPI Fetch."""

from souwen.platform.provider_spec import ClientFetchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SCRAPERAPI_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="scraperapi",
    adapter_id="scraperapi-fetch",
    adapter_reason="ScraperAPI rendering and local HTML extraction remain in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        host="api.scraperapi.com",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/"),),
    ),
    auth=AuthDeclaration(placement="query", reference="SCRAPERAPI_API_KEY", field_name="api_key"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["SCRAPERAPI_FETCH_PROFILE"]
