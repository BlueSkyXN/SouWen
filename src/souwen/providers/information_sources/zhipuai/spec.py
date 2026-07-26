"""Reviewed bridge declaration for zhipuai existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

ZHIPUAI_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="zhipuai",
    adapter_id="zhipuai-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="open.bigmodel.cn",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/api/paas/v4/tools"),),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="ZHIPUAI_API_KEY",
        field_name="Authorization",
        required=True,
    ),
    configuration_keys=("enabled",),
)
