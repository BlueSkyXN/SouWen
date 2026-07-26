"""Reviewed bridge declaration for Figshare's normalized article search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


FIGSHARE_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="figshare",
    adapter_id="figshare-search",
    domain="research_output",
    bridge_reason=(
        "Figshare's typed research-output projection retains metadata beyond the canonical Search DTO"
    ),
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="api.figshare.com",
        base_path="/v2",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/articles/search"),),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["FIGSHARE_PROVIDER_SPEC"]
