"""Reviewed bridge declaration for Diffbot Fetch."""

from souwen.platform.provider_spec import LegacyFetchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

DIFFBOT_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="diffbot",
    adapter_id="diffbot-fetch",
    bridge_reason="Diffbot Article response normalization remains in the legacy Fetch bridge",
    transport=LegacyTransportDeclaration(
        host="api.diffbot.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/v3/article"),),
    ),
    auth=AuthDeclaration(placement="query", reference="DIFFBOT_API_TOKEN", field_name="token"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["DIFFBOT_FETCH_PROFILE"]
