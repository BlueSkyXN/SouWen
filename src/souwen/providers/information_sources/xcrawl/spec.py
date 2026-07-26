"""Reviewed Search and Fetch bridge declarations for xcrawl."""

from souwen.platform.provider_spec import (
    LegacyFetchProviderSpec,
    LegacySearchProviderSpec,
    LegacyTransportDeclaration,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

_AUTH = AuthDeclaration(placement="bearer", reference="XCRAWL_API_KEY", field_name="Authorization")
_TRANSPORT = LegacyTransportDeclaration(
    host="api.xcrawl.dev",
    protocol="json",
    operations=(
        HttpOperation(method="POST", endpoint="/v1/search"),
        HttpOperation(method="POST", endpoint="/v1/scrape"),
    ),
)
XCRAWL_SEARCH_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="xcrawl",
    adapter_id="xcrawl-search",
    domain="web",
    bridge_reason="legacy response normalization requires a bridge",
    transport=_TRANSPORT,
    auth=_AUTH,
    configuration_keys=("enabled",),
)
XCRAWL_FETCH_PROVIDER_SPEC = LegacyFetchProviderSpec(
    provider_id="xcrawl",
    adapter_id="xcrawl-fetch",
    bridge_reason="legacy client owns reviewed SSRF policy and receipt parsing",
    transport=_TRANSPORT,
    auth=_AUTH,
    target_contract="public_url",
    configuration_keys=("enabled",),
)
