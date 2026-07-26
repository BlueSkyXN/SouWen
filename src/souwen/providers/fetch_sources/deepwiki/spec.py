"""Reviewed bridge declaration for DeepWiki Fetch."""

from souwen.platform.provider_spec import ClientFetchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

DEEPWIKI_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="deepwiki",
    adapter_id="deepwiki-fetch",
    adapter_reason="DeepWiki's bounded crawler and Jina fallback remain in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        host="deepwiki.com",
        protocol="multi_transport",
        operations=(HttpOperation(method="GET", endpoint="/:repository"),),
    ),
    additional_transports=(
        ClientTransportDeclaration(
            host="r.jina.ai",
            protocol="multi_transport",
            operations=(HttpOperation(method="GET", endpoint="/:target"),),
        ),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="JINA_API_KEY",
        field_name="Authorization",
        required=False,
    ),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["DEEPWIKI_FETCH_PROFILE"]
