"""Reviewed bridge declaration for github legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

GITHUB_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="github",
    adapter_id="github-search",
    domain="developer",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="api.github.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/repositories"),),
    ),
    auth=AuthDeclaration(
        placement="header",
        reference="GITHUB_TOKEN",
        field_name="Authorization",
        required=False,
    ),
    configuration_keys=("enabled",),
)
