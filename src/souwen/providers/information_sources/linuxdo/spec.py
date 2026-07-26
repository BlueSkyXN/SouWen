"""Reviewed bridge declaration for linuxdo legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

LINUXDO_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="linuxdo",
    adapter_id="linuxdo-search",
    domain="cn_tech",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="linux.do",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search.json"),),
    ),
    configuration_keys=("enabled",),
)
