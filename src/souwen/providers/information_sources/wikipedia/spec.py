"""Reviewed bridge declaration for wikipedia existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

WIKIPEDIA_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="wikipedia",
    adapter_id="wikipedia-search",
    domain="knowledge",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="zh.wikipedia.org",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/w/api.php"),),
    ),
    configuration_keys=("enabled",),
)
