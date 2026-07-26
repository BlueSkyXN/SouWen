from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

YOUTUBE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="youtube",
    adapter_id="youtube-search",
    domain="videos",
    adapter_reason="existing YouTube search normalization preserves videos-only scope",
    transport=ClientTransportDeclaration(
        host="www.googleapis.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/youtube/v3/search"),),
    ),
    auth=AuthDeclaration(placement="query", reference="YOUTUBE_API_KEY", field_name="key"),
    configuration_keys=("enabled",),
)
