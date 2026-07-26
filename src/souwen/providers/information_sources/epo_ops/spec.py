"""Reviewed OAuth bridge declaration for EPO OPS patent Search."""

from souwen.platform.provider_spec import (
    CredentialBinding,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation


EPO_OPS_BRIDGE_SPEC = LegacySearchProviderSpec(
    provider_id="epo_ops",
    adapter_id="epo_ops-search",
    domain="patent",
    bridge_reason="EPO CQL/range mapping and OAuth token acquisition remain in the legacy bridge",
    transport=LegacyTransportDeclaration(
        host="ops.epo.org",
        base_path="/3.2",
        protocol="xml",
        operations=(
            HttpOperation(method="POST", endpoint="/auth/accesstoken"),
            HttpOperation(method="GET", endpoint="/rest-services/published-data/search"),
        ),
    ),
    auth=AuthDeclaration(
        placement="oauth_body",
        reference="EPO_CONSUMER_KEY",
        field_name="client_id",
        additional_bindings=(
            CredentialBinding(
                placement="oauth_body", reference="EPO_CONSUMER_SECRET", field_name="client_secret"
            ),
        ),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["EPO_OPS_BRIDGE_SPEC"]
