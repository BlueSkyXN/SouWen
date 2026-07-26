"""Reviewed bridge declaration for scrapingdog legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SCRAPINGDOG_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="scrapingdog",
    adapter_id="scrapingdog-search",
    domain="web",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
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
