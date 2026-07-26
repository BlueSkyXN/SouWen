from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

HOSTLOC_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="hostloc",
    adapter_id="hostloc-search",
    domain="cn_tech",
    adapter_reason="DDG HTML site-search and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="html.duckduckgo.com",
        protocol="html",
        operations=(HttpOperation(method="POST", endpoint="/html/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["HOSTLOC_PROVIDER_SPEC"]
