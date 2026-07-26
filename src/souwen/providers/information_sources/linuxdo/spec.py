"""Reviewed bridge declaration for linuxdo existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

LINUXDO_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="linuxdo",
    adapter_id="linuxdo-search",
    domain="cn_tech",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="linux.do",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search.json"),),
    ),
    configuration_keys=("enabled",),
)
