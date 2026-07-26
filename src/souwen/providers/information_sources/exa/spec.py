"""Reviewed Search and Fetch bridge declarations for exa."""

from souwen.platform.provider_spec import (
    LegacyFetchProviderSpec,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

_AUTH = AuthDeclaration(placement="bearer", reference="EXA_API_KEY", field_name="Authorization")
_TRANSPORT = LegacyTransportDeclaration(
    host="api.exa.ai",
    protocol="json",
    operations=(
        HttpOperation(method="POST", endpoint="/search"),
        HttpOperation(method="POST", endpoint="/contents"),
    ),
)
EXA_SEARCH_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="exa",
    adapter_id="exa-search",
    domain="web",
    bridge_reason="legacy response normalization requires a bridge",
    transport=_TRANSPORT,
    auth=_AUTH,
    configuration_keys=("enabled",),
)
EXA_FETCH_PROVIDER_SPEC = LegacyFetchProviderSpec(
    provider_id="exa",
    adapter_id="exa-fetch",
    bridge_reason="legacy client owns reviewed SSRF policy and receipt parsing",
    transport=_TRANSPORT,
    auth=_AUTH,
    target_contract="public_url",
    configuration_keys=("enabled",),
)
