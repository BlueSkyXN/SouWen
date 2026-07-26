"""Reviewed bridge declaration for ZenRows Fetch."""

from souwen.platform.provider_spec import LegacyFetchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

ZENROWS_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="zenrows",
    adapter_id="zenrows-fetch",
    bridge_reason="ZenRows rendering and local HTML extraction remain in the legacy Fetch bridge",
    transport=LegacyTransportDeclaration(
        host="api.zenrows.com",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/v1/"),),
    ),
    auth=AuthDeclaration(placement="query", reference="ZENROWS_API_KEY", field_name="apikey"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["ZENROWS_FETCH_PROFILE"]
