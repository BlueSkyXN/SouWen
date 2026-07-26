from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

WEIBO_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="weibo",
    adapter_id="weibo-search",
    domain="social",
    bridge_reason="bounded mobile-search response normalization requires a bridge",
    transport=LegacyTransportDeclaration(
        host="m.weibo.cn",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/api/container/getIndex"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["WEIBO_PROVIDER_SPEC"]
