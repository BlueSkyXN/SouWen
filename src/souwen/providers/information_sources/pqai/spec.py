"""Reviewed bridge declaration for authenticated PQAI patent search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation


PQAI_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="pqai",
    adapter_id="pqai-search",
    domain="patent",
    adapter_reason="PQAI token query parameter and result compatibility parsing remain in the existing bridge",
    transport=ClientTransportDeclaration(
        host="api.projectpq.ai",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/102"),),
    ),
    auth=AuthDeclaration(placement="query", reference="PQAI_API_TOKEN", field_name="token"),
    configuration_keys=("enabled",),
)

__all__ = ["PQAI_BRIDGE_SPEC"]
