"""Reviewed bridge declaration for github existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

GITHUB_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="github",
    adapter_id="github-search",
    domain="developer",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
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
