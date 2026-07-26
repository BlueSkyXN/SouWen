"""Reviewed bridge declaration for Zenodo publication search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

ZENODO_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="zenodo",
    adapter_id="zenodo-search",
    bridge_reason="record identity and legacy total normalization require a bridge",
    transport=LegacyTransportDeclaration(
        host="zenodo.org",
        base_path="/api",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/records"),),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="ZENODO_ACCESS_TOKEN",
        field_name="Authorization",
        required=False,
    ),
    configuration_keys=("enabled",),
)
