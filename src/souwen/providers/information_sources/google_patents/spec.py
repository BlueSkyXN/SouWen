"""Reviewed bridge declaration for the existing Google Patents scraper."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


GOOGLE_PATENTS_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="google_patents",
    adapter_id="google_patents-search",
    adapter_reason="XHR, HTML, and browser fallback parsing remain in the existing scraper bridge",
    domain="patent",
    transport=ClientTransportDeclaration(
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
