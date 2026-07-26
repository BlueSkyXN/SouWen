from souwen.platform.provider_spec import (
    HttpOperation,
    ClientSearchProviderSpec,
    SelfHostedTransportDeclaration,
)

SEARXNG_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="searxng",
    adapter_id="searxng-search",
    domain="web",
    adapter_reason="self-hosted JSON search parsing remains behind a strict Search bridge",
    transport=SelfHostedTransportDeclaration(
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled", "base_url"),
)
