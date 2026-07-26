"""Reviewed bridge declaration for serper legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SERPER_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="serper",
    adapter_id="serper-search",
    domain="web",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="google.serper.dev",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/search"),),
    ),
    auth=AuthDeclaration(
        placement="header",
        reference="SERPER_API_KEY",
        field_name="X-API-KEY",
        required=True,
    ),
    configuration_keys=("enabled",),
)
