"""Reviewed Search and Fetch bridge declarations for firecrawl."""

from souwen.platform.provider_spec import (
    LegacyFetchProviderSpec,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

_AUTH = AuthDeclaration(
    placement="bearer", reference="FIRECRAWL_API_KEY", field_name="Authorization"
)
_TRANSPORT = LegacyTransportDeclaration(
    host="api.firecrawl.dev",
    protocol="json",
    operations=(
        HttpOperation(method="POST", endpoint="/v1/search"),
        HttpOperation(method="POST", endpoint="/v1/scrape"),
    ),
)
FIRECRAWL_SEARCH_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="firecrawl",
    adapter_id="firecrawl-search",
    domain="web",
    bridge_reason="legacy response normalization requires a bridge",
    transport=_TRANSPORT,
    auth=_AUTH,
    configuration_keys=("enabled",),
)
FIRECRAWL_FETCH_PROVIDER_SPEC = LegacyFetchProviderSpec(
    provider_id="firecrawl",
    adapter_id="firecrawl-fetch",
    bridge_reason="legacy client owns reviewed SSRF policy and receipt parsing",
    transport=_TRANSPORT,
    auth=_AUTH,
    target_contract="public_url",
    configuration_keys=("enabled",),
)
