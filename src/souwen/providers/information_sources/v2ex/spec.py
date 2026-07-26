from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

V2EX_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="v2ex",
    adapter_id="v2ex-search",
    domain="cn_tech",
    adapter_reason="DDG HTML site-search and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="html.duckduckgo.com",
        protocol="html",
        operations=(HttpOperation(method="POST", endpoint="/html/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["V2EX_PROVIDER_SPEC"]
