"""Reviewed bridge declaration for facebook legacy Search."""

from souwen.platform.provider_spec import (
    CredentialBinding,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

FACEBOOK_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="facebook",
    adapter_id="facebook-search",
    domain="social",
    bridge_reason=(
        "legacy client derives one Bearer App Access Token as app_id|app_secret before "
        "WebSearchResponse normalization"
    ),
    transport=LegacyTransportDeclaration(
        host="graph.facebook.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/v19.0/pages/search"),),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="FACEBOOK_APP_ID",
        field_name="Authorization",
        required=True,
        additional_bindings=(
            CredentialBinding(
                placement="bearer",
                reference="FACEBOOK_APP_SECRET",
                field_name="Authorization",
                required=True,
            ),
        ),
    ),
    configuration_keys=("enabled",),
)
