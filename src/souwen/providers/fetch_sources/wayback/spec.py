from souwen.platform.provider_spec import LegacyFetchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

WAYBACK_FETCH_PROVIDER_SPEC = LegacyFetchProviderSpec(
    provider_id="wayback",
    adapter_id="wayback-fetch",
    bridge_reason="legacy Wayback client owns availability lookup, SSRF policy, and archived-content parsing",
    transport=LegacyTransportDeclaration(
        host="archive.org",
        protocol="multi_transport",
        operations=(HttpOperation(method="GET", endpoint="/wayback/available"),),
    ),
    additional_transports=(
        LegacyTransportDeclaration(
            host="web.archive.org",
            protocol="multi_transport",
            operations=(HttpOperation(method="GET", endpoint="/web/:snapshot/:target"),),
        ),
    ),
    target_contract="public_url",
    configuration_keys=("enabled",),
)
