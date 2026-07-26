"""Static reviewed OpenAlex REST declaration for generic-provider intake."""

from souwen.platform.provider_spec import RestJsonProviderSpec

OPENALEX_REST_SPEC = RestJsonProviderSpec(
    provider_id="openalex",
    adapter_id="openalex-search",
    adapter_kind="legacy_bridge",
    review_status="bridge_exception",
    bridge_reason="legacy filter and DOI fallback projection require a reviewed mapping migration",
    host="api.openalex.org",
    base_path="/works",
    configuration_keys=("enabled",),
)

__all__ = ["OPENALEX_REST_SPEC"]
