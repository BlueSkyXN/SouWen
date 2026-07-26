"""Reviewed bridge declaration for authenticated USPTO ODP application search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation


USPTO_ODP_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="uspto_odp",
    adapter_id="uspto_odp-search",
    domain="patent",
    adapter_reason="USPTO application response compatibility parsing remains in the existing bridge",
    transport=ClientTransportDeclaration(
        host="data.uspto.gov",
        base_path="/api/v1",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/patent/applications"),),
    ),
    auth=AuthDeclaration(placement="header", reference="USPTO_API_KEY", field_name="X-API-Key"),
    configuration_keys=("enabled",),
)

__all__ = ["USPTO_ODP_BRIDGE_SPEC"]
