"""Reviewed Search and Fetch bridge declarations for xcrawl."""

from souwen.platform.provider_spec import (
    ClientFetchProviderSpec,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

_AUTH = AuthDeclaration(placement="bearer", reference="XCRAWL_API_KEY", field_name="Authorization")
_TRANSPORT = ClientTransportDeclaration(
    host="api.xcrawl.dev",
    protocol="json",
    operations=(
        HttpOperation(method="POST", endpoint="/v1/search"),
        HttpOperation(method="POST", endpoint="/v1/scrape"),
    ),
)
XCRAWL_SEARCH_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="xcrawl",
    adapter_id="xcrawl-search",
    domain="web",
    adapter_reason="existing response normalization requires a bridge",
    transport=_TRANSPORT,
    auth=_AUTH,
    configuration_keys=("enabled",),
)
XCRAWL_FETCH_PROVIDER_SPEC = ClientFetchProviderSpec(
    provider_id="xcrawl",
    adapter_id="xcrawl-fetch",
    adapter_reason="existing client owns reviewed SSRF policy and receipt parsing",
    transport=_TRANSPORT,
    auth=_AUTH,
    target_contract="public_url",
    configuration_keys=("enabled",),
)
