"""Reviewed bridge declaration for feishu_drive legacy Search."""

from souwen.platform.provider_spec import (
    CredentialBinding,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

FEISHU_DRIVE_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="feishu_drive",
    adapter_id="feishu-drive-search",
    domain="office",
    bridge_reason=(
        "legacy client exchanges app credentials for a tenant token before the suite docs search"
    ),
    transport=LegacyTransportDeclaration(
        host="open.feishu.cn",
        protocol="json",
        operations=(
            HttpOperation(
                method="POST",
                endpoint="/open-apis/auth/v3/tenant_access_token/internal",
            ),
            HttpOperation(
                method="POST",
                endpoint="/open-apis/suite/docs-api/search/object",
            ),
        ),
    ),
    auth=AuthDeclaration(
        placement="oauth_body",
        reference="FEISHU_APP_ID",
        field_name="app_id",
        required=True,
        additional_bindings=(
            CredentialBinding(
                placement="oauth_body",
                reference="FEISHU_APP_SECRET",
                field_name="app_secret",
                required=True,
            ),
        ),
    ),
    configuration_keys=("enabled",),
)
