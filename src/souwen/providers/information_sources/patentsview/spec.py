"""Static reviewed PatentsView REST declaration for generic-provider intake."""

from souwen.platform.provider_spec import RestJsonProviderSpec
from souwen.platform.provider_spec.models import AuthDeclaration

PATENTSVIEW_REST_SPEC = RestJsonProviderSpec(
    provider_id="patentsview",
    adapter_id="patentsview-search",
    domain="patent",
    adapter_kind="legacy_bridge",
    review_status="bridge_exception",
    bridge_reason="legacy patent response projection has not yet been expressed as generic mapping",
    host="search.patentsview.org",
    base_path="/api/v1",
    auth=AuthDeclaration(
        placement="header", reference="PATENTSVIEW_API_KEY", field_name="X-Api-Key"
    ),
    configuration_keys=("enabled", "max_retries", "timeout_seconds"),
)

__all__ = ["PATENTSVIEW_REST_SPEC"]
