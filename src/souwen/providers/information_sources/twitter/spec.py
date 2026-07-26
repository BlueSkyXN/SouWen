"""Reviewed bridge declaration for twitter existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

TWITTER_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="twitter",
    adapter_id="twitter-search",
    domain="social",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
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
