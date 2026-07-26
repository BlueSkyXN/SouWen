"""Reviewed Search and Fetch bridge declarations for exa."""

from souwen.platform.provider_spec import (
    ClientFetchProviderSpec,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

_AUTH = AuthDeclaration(placement="bearer", reference="EXA_API_KEY", field_name="Authorization")
_TRANSPORT = ClientTransportDeclaration(
    host="api.exa.ai",
    protocol="json",
    operations=(
        HttpOperation(method="POST", endpoint="/search"),
        HttpOperation(method="POST", endpoint="/contents"),
    ),
)
EXA_SEARCH_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="exa",
    adapter_id="exa-search",
    domain="web",
    adapter_reason="existing response normalization requires a bridge",
    transport=_TRANSPORT,
    auth=_AUTH,
    configuration_keys=("enabled",),
)
EXA_FETCH_PROVIDER_SPEC = ClientFetchProviderSpec(
    provider_id="exa",
    adapter_id="exa-fetch",
    adapter_reason="existing client owns reviewed SSRF policy and receipt parsing",
    transport=_TRANSPORT,
    auth=_AUTH,
    target_contract="public_url",
    configuration_keys=("enabled",),
)
