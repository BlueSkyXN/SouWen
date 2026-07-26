"""Reviewed bridge declaration for wikipedia legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

WIKIPEDIA_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="wikipedia",
    adapter_id="wikipedia-search",
    domain="knowledge",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="zh.wikipedia.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/w/api.php"),),
    ),
    configuration_keys=("enabled",),
)
