"""Reviewed Search and Fetch bridge declarations for kimi_code."""

from souwen.platform.provider_spec import (
    ClientFetchProviderSpec,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

_AUTH = AuthDeclaration(
    placement="bearer", reference="KIMI_CODE_API_KEY", field_name="Authorization"
)
_TRANSPORT = ClientTransportDeclaration(
    host="api.kimi.com",
    protocol="json",
    operations=(
        HttpOperation(method="POST", endpoint="/v1/search"),
        HttpOperation(method="POST", endpoint="/v1/fetch"),
    ),
)
KIMI_CODE_SEARCH_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="kimi_code",
    adapter_id="kimi_code-search",
    domain="web",
    adapter_reason="existing response normalization requires a bridge",
    transport=_TRANSPORT,
    auth=_AUTH,
    configuration_keys=("enabled",),
)
KIMI_CODE_FETCH_PROVIDER_SPEC = ClientFetchProviderSpec(
    provider_id="kimi_code",
    adapter_id="kimi_code-fetch",
    adapter_reason="existing client owns reviewed SSRF policy and receipt parsing",
    transport=_TRANSPORT,
    auth=_AUTH,
    target_contract="public_url",
    configuration_keys=("enabled",),
)
