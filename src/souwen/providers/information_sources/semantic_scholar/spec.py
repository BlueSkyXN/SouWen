"""Reviewed bridge declaration for Semantic Scholar paper search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

SEMANTIC_SCHOLAR_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="semantic_scholar",
    adapter_id="semantic-scholar-search",
    adapter_reason="paper-id canonicalization is derived from existing record URLs",
    transport=ClientTransportDeclaration(
        host="api.semanticscholar.org",
        base_path="/graph/v1",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/paper/search"),),
    ),
    auth=AuthDeclaration(
        placement="header",
        reference="SEMANTIC_SCHOLAR_API_KEY",
        field_name="x-api-key",
        required=False,
    ),
    configuration_keys=("enabled",),
)
