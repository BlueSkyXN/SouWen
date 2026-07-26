"""Reviewed bridge declaration for the two-stage PMC XML search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation


PMC_BRIDGE_SPEC = LegacySearchProviderSpec(
    provider_id="pmc",
    adapter_id="pmc-search",
    bridge_reason="NCBI esearch and JATS efetch XML parsing remain in the legacy PMC bridge",
    auth=AuthDeclaration(
        placement="query", reference="PUBMED_API_KEY", field_name="api_key", required=False
    ),
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="eutils.ncbi.nlm.nih.gov",
        base_path="/entrez/eutils",
        protocol="multi_step_xml",
        operations=(
            HttpOperation(method="GET", endpoint="/esearch.fcgi"),
            HttpOperation(method="GET", endpoint="/efetch.fcgi"),
        ),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["PMC_BRIDGE_SPEC"]
