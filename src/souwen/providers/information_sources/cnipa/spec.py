"""Reviewed OAuth bridge declaration for CNIPA patent Search."""

from souwen.platform.provider_spec import (
    CredentialBinding,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation


CNIPA_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="cnipa",
    adapter_id="cnipa-search",
    domain="patent",
    adapter_reason="CNIPA OAuth token acquisition and response compatibility parsing remain in the existing bridge",
    transport=ClientTransportDeclaration(
        host="open.cnipr.com",
        protocol="json",
        operations=(
            HttpOperation(method="POST", endpoint="/oauth/token"),
            HttpOperation(method="GET", endpoint="/api/search"),
        ),
    ),
    auth=AuthDeclaration(
        placement="oauth_body",
        reference="CNIPA_CLIENT_ID",
        field_name="client_id",
        additional_bindings=(
            CredentialBinding(
                placement="oauth_body", reference="CNIPA_CLIENT_SECRET", field_name="client_secret"
            ),
        ),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["CNIPA_BRIDGE_SPEC"]
