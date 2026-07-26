"""Reviewed bridge declaration for authenticated PatSnap patent search."""

from souwen.platform.provider_spec import (
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation


PATSNAP_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="patsnap",
    adapter_id="patsnap-search",
    domain="patent",
    adapter_reason="PatSnap response compatibility parsing remains in the existing search bridge",
    transport=ClientTransportDeclaration(
        host="connect.patsnap.com",
        base_path="/open/api",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/patent/search"),),
    ),
    auth=AuthDeclaration(
        placement="header", reference="PATSNAP_API_KEY", field_name="X-PatSnap-Key"
    ),
    configuration_keys=("enabled",),
)

__all__ = ["PATSNAP_BRIDGE_SPEC"]
