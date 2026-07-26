"""Reviewed bridge declaration for scrapingdog existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SCRAPINGDOG_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="scrapingdog",
    adapter_id="scrapingdog-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="api.scrapingdog.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/google"),),
    ),
    auth=AuthDeclaration(
        placement="query",
        reference="SCRAPINGDOG_API_KEY",
        field_name="api_key",
        required=True,
    ),
    configuration_keys=("enabled",),
)
