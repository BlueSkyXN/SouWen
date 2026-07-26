from souwen.platform.provider_spec import ClientFetchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

WAYBACK_FETCH_PROVIDER_SPEC = ClientFetchProviderSpec(
    provider_id="wayback",
    adapter_id="wayback-fetch",
    adapter_reason="existing Wayback client owns availability lookup, SSRF policy, and archived-content parsing",
    transport=ClientTransportDeclaration(
        host="archive.org",
        protocol="multi_transport",
        operations=(HttpOperation(method="GET", endpoint="/wayback/available"),),
    ),
    additional_transports=(
        ClientTransportDeclaration(
            host="web.archive.org",
            protocol="multi_transport",
            operations=(HttpOperation(method="GET", endpoint="/web/:snapshot/:target"),),
        ),
    ),
    target_contract="public_url",
    configuration_keys=("enabled",),
)
