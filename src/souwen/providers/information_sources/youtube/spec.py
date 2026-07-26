from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

YOUTUBE_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="youtube",
    adapter_id="youtube-search",
    domain="videos",
    bridge_reason="legacy YouTube search normalization preserves videos-only scope",
    transport=LegacyTransportDeclaration(
        host="www.googleapis.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/youtube/v3/search"),),
    ),
    auth=AuthDeclaration(placement="query", reference="YOUTUBE_API_KEY", field_name="key"),
    configuration_keys=("enabled",),
)
