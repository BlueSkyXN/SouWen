"""Reviewed Search and Fetch bridge declarations for tavily."""

from souwen.platform.provider_spec import (
    ClientFetchProviderSpec,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

_AUTH = AuthDeclaration(placement="bearer", reference="TAVILY_API_KEY", field_name="Authorization")
_TRANSPORT = ClientTransportDeclaration(
    host="api.tavily.com",
    protocol="json",
    operations=(
        HttpOperation(method="POST", endpoint="/search"),
        HttpOperation(method="POST", endpoint="/extract"),
    ),
)
TAVILY_SEARCH_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="tavily",
    adapter_id="tavily-search",
    domain="web",
    adapter_reason="existing response normalization requires a bridge",
    transport=_TRANSPORT,
    auth=_AUTH,
    configuration_keys=("enabled",),
)
TAVILY_FETCH_PROVIDER_SPEC = ClientFetchProviderSpec(
    provider_id="tavily",
    adapter_id="tavily-fetch",
    adapter_reason="existing client owns reviewed SSRF policy and receipt parsing",
    transport=_TRANSPORT,
    auth=_AUTH,
    target_contract="public_url",
    configuration_keys=("enabled",),
)
