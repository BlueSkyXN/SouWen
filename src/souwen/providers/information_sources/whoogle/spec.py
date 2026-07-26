from souwen.platform.provider_spec import (
    HttpOperation,
    LegacySearchProviderSpec,
    SelfHostedTransportDeclaration,
)

WHOOGLE_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="whoogle",
    adapter_id="whoogle-search",
    domain="web",
    bridge_reason="self-hosted HTML search parsing remains behind a strict Search bridge",
    transport=SelfHostedTransportDeclaration(
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/search"),),
    ),
    configuration_keys=("enabled", "base_url"),
)
