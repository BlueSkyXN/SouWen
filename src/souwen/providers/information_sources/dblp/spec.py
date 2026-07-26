"""Reviewed bridge declaration for the DBLP search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

DBLP_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="dblp",
    adapter_id="dblp-search",
    review_status="reviewed_adapter",
    adapter_reason="existing records do not guarantee one reviewed stable generic identifier",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="dblp.org",
        base_path="/search",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/publ/api"),),
    ),
    configuration_keys=("enabled",),
)
