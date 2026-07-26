"""Reviewed bridge declaration for linkup legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

LINKUP_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="linkup",
    adapter_id="linkup-search",
    domain="web",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="api.linkup.so",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/v1/search"),),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="LINKUP_API_KEY",
        field_name="Authorization",
        required=True,
    ),
    configuration_keys=("enabled",),
)
