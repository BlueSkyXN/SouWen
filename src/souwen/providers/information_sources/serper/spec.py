"""Reviewed bridge declaration for serper existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SERPER_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="serper",
    adapter_id="serper-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
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
