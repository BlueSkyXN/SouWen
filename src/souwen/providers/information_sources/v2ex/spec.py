from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

V2EX_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="v2ex",
    adapter_id="v2ex-search",
    domain="cn_tech",
    bridge_reason="DDG HTML site-search and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="html.duckduckgo.com",
        protocol="html",
        operations=(HttpOperation(method="POST", endpoint="/html/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["V2EX_PROVIDER_SPEC"]
