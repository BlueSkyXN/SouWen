from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

COOLAPK_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="coolapk",
    adapter_id="coolapk-search",
    domain="cn_tech",
    bridge_reason="DDG HTML site-search and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="html.duckduckgo.com",
        protocol="html",
        operations=(HttpOperation(method="POST", endpoint="/html/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["COOLAPK_PROVIDER_SPEC"]
