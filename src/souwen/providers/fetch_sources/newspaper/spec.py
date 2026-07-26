from souwen.platform.provider_spec import LegacyFetchProviderSpec, PublicTargetDeclaration


NEWSPAPER_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="newspaper",
    adapter_id="newspaper-fetch",
    bridge_reason="newspaper4k parsing remains behind the IP-bound public-target Fetch bridge",
    transport=PublicTargetDeclaration(),
    target_contract="public_url",
    configuration_keys=("enabled",),
)

__all__ = ["NEWSPAPER_FETCH_PROFILE"]
