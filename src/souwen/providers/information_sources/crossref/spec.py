"""Reviewed bridge declaration for the Crossref search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

CROSSREF_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="crossref",
    adapter_id="crossref-search",
    review_status="reviewed_adapter",
    adapter_reason="existing free-form filters and DOI-only canonical identity require custom projection",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="api.crossref.org",
        base_path="/",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/works"),),
    ),
    configuration_keys=("enabled",),
)
