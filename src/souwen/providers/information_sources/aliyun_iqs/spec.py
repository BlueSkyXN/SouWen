"""Reviewed bridge declaration for aliyun_iqs existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

ALIYUN_IQS_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="aliyun_iqs",
    adapter_id="aliyun-iqs-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
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
