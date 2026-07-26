from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

ZHIHU_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="zhihu",
    adapter_id="zhihu-search",
    domain="social",
    adapter_reason="bounded public-search JSON normalization requires a bridge",
    transport=ClientTransportDeclaration(
        host="www.zhihu.com",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/api/v4/search_v3"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["ZHIHU_PROVIDER_SPEC"]
