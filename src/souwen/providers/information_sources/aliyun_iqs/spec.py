"""Reviewed bridge declaration for aliyun_iqs legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

ALIYUN_IQS_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="aliyun_iqs",
    adapter_id="aliyun-iqs-search",
    domain="web",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
        host="cloud-iqs.aliyuncs.com",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/search/llm"),),
    ),
    auth=AuthDeclaration(
        placement="header",
        reference="ALIYUN_IQS_API_KEY",
        field_name="X-API-Key",
        required=True,
    ),
    configuration_keys=("enabled",),
)
