"""Reviewed bridge declaration for stackoverflow legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

STACKOVERFLOW_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="stackoverflow",
    adapter_id="stackoverflow-search",
    domain="developer",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="api.stackexchange.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/2.3/search/advanced"),),
    ),
    auth=AuthDeclaration(
        placement="query",
        reference="STACKOVERFLOW_API_KEY",
        field_name="key",
        required=False,
    ),
    configuration_keys=("enabled",),
)
