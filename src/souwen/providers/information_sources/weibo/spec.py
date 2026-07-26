from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

WEIBO_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="weibo",
    adapter_id="weibo-search",
    domain="social",
    adapter_reason="bounded mobile-search response normalization requires a bridge",
    transport=ClientTransportDeclaration(
        host="m.weibo.cn",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/api/container/getIndex"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["WEIBO_PROVIDER_SPEC"]
