"""Reviewed bridge declaration for the legacy arXiv Atom search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

ARXIV_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="arxiv",
    adapter_id="arxiv-search",
    bridge_reason="legacy client parses Atom XML and preserves reviewed query construction",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="export.arxiv.org",
        base_path="/api",
        protocol="atom_xml",
        operations=(HttpOperation(method="GET", endpoint="/query"),),
    ),
    configuration_keys=("enabled",),
)
