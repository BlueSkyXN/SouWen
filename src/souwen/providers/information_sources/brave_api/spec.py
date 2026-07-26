"""Reviewed bridge declaration for brave_api legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

BRAVE_API_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="brave_api",
    adapter_id="brave-api-search",
    domain="web",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
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
