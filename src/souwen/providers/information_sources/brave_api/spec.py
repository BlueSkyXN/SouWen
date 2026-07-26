"""Reviewed bridge declaration for brave_api existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

BRAVE_API_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="brave_api",
    adapter_id="brave-api-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="api.search.brave.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/res/v1/web/search"),),
    ),
    auth=AuthDeclaration(
        placement="header",
        reference="BRAVE_API_KEY",
        field_name="X-Subscription-Token",
        required=True,
    ),
    configuration_keys=("enabled",),
)
