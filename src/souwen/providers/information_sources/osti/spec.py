"""Reviewed bridge declaration for OSTI's list-shaped JSON Search response."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


OSTI_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="osti",
    adapter_id="osti-search",
    adapter_reason="OSTI total metadata is an HTTP header and the existing client owns list-response parsing",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="www.osti.gov",
        base_path="/api/v1",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/records"),),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["OSTI_BRIDGE_SPEC"]
