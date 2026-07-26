"""Reviewed bridge declaration for serpapi existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SERPAPI_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="serpapi",
    adapter_id="serpapi-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="serpapi.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    auth=AuthDeclaration(
        placement="query",
        reference="SERPAPI_API_KEY",
        field_name="api_key",
        required=True,
    ),
    configuration_keys=("enabled",),
)
