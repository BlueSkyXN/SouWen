from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

JUEJIN_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="juejin",
    adapter_id="juejin-search",
    domain="cn_tech",
    bridge_reason="legacy cursor-paged JSON normalization requires a first-page bridge",
    transport=LegacyTransportDeclaration(
        host="api.juejin.cn",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search_api/v1/search"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["JUEJIN_PROVIDER_SPEC"]
