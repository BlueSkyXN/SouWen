"""Reviewed bridge declaration for facebook existing Search."""

from souwen.platform.provider_spec import (
    CredentialBinding,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

FACEBOOK_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="facebook",
    adapter_id="facebook-search",
    domain="social",
    adapter_reason=(
        "existing client derives one Bearer App Access Token as app_id|app_secret before "
        "WebSearchResponse normalization"
    ),
    transport=ClientTransportDeclaration(
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
