"""Reviewed bridge declaration for authenticated The Lens patent search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation


THE_LENS_BRIDGE_SPEC = LegacySearchProviderSpec(
    provider_id="the_lens",
    adapter_id="the_lens-search",
    domain="patent",
    bridge_reason="The Lens DSL request construction and quota-header handling remain in the legacy bridge",
    transport=LegacyTransportDeclaration(
        host="api.lens.org",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/patent/search"),),
    ),
    auth=AuthDeclaration(
        placement="bearer", reference="LENS_API_TOKEN", field_name="Authorization"
    ),
    configuration_keys=("enabled",),
)

__all__ = ["THE_LENS_BRIDGE_SPEC"]
