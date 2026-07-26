"""Reviewed bridge declaration for Cloudflare Browser Rendering Fetch."""

from souwen.platform.provider_spec import (
    CredentialBinding,
    LegacyFetchProviderSpec,
    LegacyTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

CLOUDFLARE_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="cloudflare",
    adapter_id="cloudflare-fetch",
    bridge_reason="Cloudflare Browser Rendering markdown fallback remains in the legacy Fetch bridge",
    transport=LegacyTransportDeclaration(
        host="api.cloudflare.com",
        protocol="json",
        operations=(
            HttpOperation(
                method="POST",
                endpoint="/client/v4/accounts/:account_id/browser-rendering/markdown",
            ),
            HttpOperation(
                method="POST",
                endpoint="/client/v4/accounts/:account_id/browser-rendering/content",
            ),
        ),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="CLOUDFLARE_API_TOKEN",
        field_name="Authorization",
        additional_bindings=(
            CredentialBinding(
                placement="path", reference="CLOUDFLARE_ACCOUNT_ID", field_name="account_id"
            ),
        ),
    ),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["CLOUDFLARE_FETCH_PROFILE"]
