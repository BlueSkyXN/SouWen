from souwen.platform.provider_spec import (
    HttpOperation,
    ClientSearchProviderSpec,
    SelfHostedTransportDeclaration,
)

WHOOGLE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="whoogle",
    adapter_id="whoogle-search",
    domain="web",
    adapter_reason="self-hosted HTML search parsing remains behind a strict Search bridge",
    transport=SelfHostedTransportDeclaration(
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled", "base_url"),
)
