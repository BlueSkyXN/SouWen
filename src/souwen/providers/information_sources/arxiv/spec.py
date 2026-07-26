"""Reviewed bridge declaration for the existing arXiv Atom search client."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

ARXIV_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="arxiv",
    adapter_id="arxiv-search",
    adapter_reason="existing client parses Atom XML and preserves reviewed query construction",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="export.arxiv.org",
        base_path="/api",
        protocol="atom_xml",
        operations=(HttpOperation(method="GET", endpoint="/query"),),
    ),
    configuration_keys=("enabled",),
)
