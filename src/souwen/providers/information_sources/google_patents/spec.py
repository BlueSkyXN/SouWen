"""Reviewed bridge declaration for the legacy Google Patents scraper."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


GOOGLE_PATENTS_BRIDGE_SPEC = LegacySearchProviderSpec(
    provider_id="google_patents",
    adapter_id="google_patents-search",
    bridge_reason="XHR, HTML, and browser fallback parsing remain in the legacy scraper bridge",
    domain="patent",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="patents.google.com",
        protocol="multi_transport",
        operations=(
            HttpOperation(method="GET", endpoint="/xhr/query"),
            HttpOperation(method="GET", endpoint="/"),
        ),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["GOOGLE_PATENTS_BRIDGE_SPEC"]
