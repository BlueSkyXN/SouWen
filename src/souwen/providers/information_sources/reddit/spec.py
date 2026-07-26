"""Reviewed bridge declaration for reddit existing Search."""

from souwen.platform.provider_spec import (
    CredentialBinding,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

REDDIT_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="reddit",
    adapter_id="reddit-search",
    domain="social",
    adapter_reason=(
        "existing bridge supports anonymous search or optional Basic client credentials followed "
        "by a derived Bearer token on oauth.reddit.com"
    ),
    transport=ClientTransportDeclaration(
        host="www.reddit.com",
        protocol="json",
        operations=(
            HttpOperation(method="GET", endpoint="/search.json"),
            HttpOperation(method="POST", endpoint="/api/v1/access_token"),
        ),
    ),
    additional_transports=(
        ClientTransportDeclaration(
            host="oauth.reddit.com",
            protocol="json",
            operations=(HttpOperation(method="GET", endpoint="/search"),),
        ),
    ),
    auth=AuthDeclaration(
        placement="header",
        reference="REDDIT_CLIENT_ID",
        field_name="Authorization",
        required=False,
        additional_bindings=(
            CredentialBinding(
                placement="header",
                reference="REDDIT_CLIENT_SECRET",
                field_name="Authorization",
                required=False,
            ),
        ),
    ),
    configuration_keys=("enabled",),
)
