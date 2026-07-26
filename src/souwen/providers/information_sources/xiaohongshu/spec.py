from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

XIAOHONGSHU_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="xiaohongshu",
    adapter_id="xiaohongshu-search",
    domain="cn_tech",
    bridge_reason="DDG HTML site-search and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="html.duckduckgo.com",
        protocol="html",
        operations=(HttpOperation(method="POST", endpoint="/html/"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["XIAOHONGSHU_PROVIDER_SPEC"]
