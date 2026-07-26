from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

ZHIHU_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="zhihu",
    adapter_id="zhihu-search",
    domain="social",
    bridge_reason="bounded public-search JSON normalization requires a bridge",
    transport=LegacyTransportDeclaration(
        host="www.zhihu.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/api/v4/search_v3"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["ZHIHU_PROVIDER_SPEC"]
