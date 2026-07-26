"""Reviewed bridge declaration for authenticated PQAI patent search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation


PQAI_BRIDGE_SPEC = LegacySearchProviderSpec(
    provider_id="pqai",
    adapter_id="pqai-search",
    domain="patent",
    bridge_reason="PQAI token query parameter and result compatibility parsing remain in the legacy bridge",
    transport=LegacyTransportDeclaration(
        host="api.projectpq.ai",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/102"),),
    ),
    auth=AuthDeclaration(placement="query", reference="PQAI_API_TOKEN", field_name="token"),
    configuration_keys=("enabled",),
)

__all__ = ["PQAI_BRIDGE_SPEC"]
