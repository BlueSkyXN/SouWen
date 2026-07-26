"""Reviewed bridge declaration for twitter legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

TWITTER_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="twitter",
    adapter_id="twitter-search",
    domain="social",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="api.twitter.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/2/tweets/search/recent"),),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="TWITTER_BEARER_TOKEN",
        field_name="Authorization",
        required=True,
    ),
    configuration_keys=("enabled",),
)
