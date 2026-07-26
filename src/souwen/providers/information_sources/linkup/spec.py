"""Reviewed bridge declaration for linkup existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

LINKUP_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="linkup",
    adapter_id="linkup-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
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
