"""Reviewed bridge declaration for serpapi legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SERPAPI_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="serpapi",
    adapter_id="serpapi-search",
    domain="web",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
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
