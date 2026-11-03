"""Reviewed bridge declaration for keenable existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

KEENABLE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="keenable",
    adapter_id="keenable-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="api.keenable.ai",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/v1/search"),),
    ),
    auth=AuthDeclaration(
        placement="header",
        reference="KEENABLE_API_KEY",
        field_name="X-API-Key",
        required=True,
    ),
    configuration_keys=("enabled",),
)
