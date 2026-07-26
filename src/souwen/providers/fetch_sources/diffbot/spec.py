"""Reviewed bridge declaration for Diffbot Fetch."""

from souwen.platform.provider_spec import ClientFetchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

DIFFBOT_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="diffbot",
    adapter_id="diffbot-fetch",
    adapter_reason="Diffbot Article response normalization remains in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        host="api.diffbot.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/v3/article"),),
    ),
    auth=AuthDeclaration(placement="query", reference="DIFFBOT_API_TOKEN", field_name="token"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["DIFFBOT_FETCH_PROFILE"]
