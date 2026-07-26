"""Reviewed Search and Fetch bridge declarations for firecrawl."""

from souwen.platform.provider_spec import (
    ClientFetchProviderSpec,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

_AUTH = AuthDeclaration(
    placement="bearer", reference="FIRECRAWL_API_KEY", field_name="Authorization"
)
_TRANSPORT = ClientTransportDeclaration(
    host="api.firecrawl.dev",
    protocol="json",
    operations=(
        HttpOperation(method="POST", endpoint="/v1/search"),
        HttpOperation(method="POST", endpoint="/v1/scrape"),
    ),
)
FIRECRAWL_SEARCH_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="firecrawl",
    adapter_id="firecrawl-search",
    domain="web",
    adapter_reason="existing response normalization requires a bridge",
    transport=_TRANSPORT,
    auth=_AUTH,
    configuration_keys=("enabled",),
)
FIRECRAWL_FETCH_PROVIDER_SPEC = ClientFetchProviderSpec(
    provider_id="firecrawl",
    adapter_id="firecrawl-fetch",
    adapter_reason="existing client owns reviewed SSRF policy and receipt parsing",
    transport=_TRANSPORT,
    auth=_AUTH,
    target_contract="public_url",
    configuration_keys=("enabled",),
)
