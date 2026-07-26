"""Reviewed bridge declaration for reddit legacy Search."""

from souwen.platform.provider_spec import (
    CredentialBinding,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

REDDIT_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="reddit",
    adapter_id="reddit-search",
    domain="social",
    bridge_reason=(
        "legacy bridge supports anonymous search or optional Basic client credentials followed "
        "by a derived Bearer token on oauth.reddit.com"
    ),
    transport=LegacyTransportDeclaration(
        host="www.reddit.com",
        protocol="json",
        operations=(
            HttpOperation(method="GET", endpoint="/search.json"),
            HttpOperation(method="POST", endpoint="/api/v1/access_token"),
        ),
    ),
    additional_transports=(
        LegacyTransportDeclaration(
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
