"""Reviewed bridge declaration for zhipuai legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

ZHIPUAI_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="zhipuai",
    adapter_id="zhipuai-search",
    domain="web",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
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
