from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

CSDN_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="csdn",
    adapter_id="csdn-search",
    domain="cn_tech",
    adapter_reason="existing paged JSON response normalization requires a bridge",
    transport=ClientTransportDeclaration(
        host="so.csdn.net",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/api/v3/search"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["CSDN_PROVIDER_SPEC"]
