from souwen.platform.provider_spec import LegacyFetchProviderSpec, PublicTargetDeclaration


READABILITY_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="readability",
    adapter_id="readability-fetch",
    bridge_reason="Readability extraction remains behind the IP-bound public-target Fetch bridge",
    transport=PublicTargetDeclaration(),
    target_contract="public_url",
    configuration_keys=("enabled",),
)

__all__ = ["READABILITY_FETCH_PROFILE"]
