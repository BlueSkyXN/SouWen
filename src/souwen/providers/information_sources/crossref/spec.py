"""Reviewed bridge declaration for the Crossref search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

CROSSREF_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="crossref",
    adapter_id="crossref-search",
    review_status="bridge_exception",
    bridge_reason="legacy free-form filters and DOI-only canonical identity require custom projection",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="api.crossref.org",
        base_path="/",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/works"),),
    ),
    configuration_keys=("enabled",),
)
