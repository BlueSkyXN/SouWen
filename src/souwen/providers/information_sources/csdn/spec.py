from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

CSDN_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="csdn",
    adapter_id="csdn-search",
    domain="cn_tech",
    bridge_reason="legacy paged JSON response normalization requires a bridge",
    transport=LegacyTransportDeclaration(
        host="so.csdn.net",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/api/v3/search"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["CSDN_PROVIDER_SPEC"]
