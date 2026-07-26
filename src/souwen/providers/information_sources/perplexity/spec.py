"""Reviewed bridge declaration for perplexity existing Search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

PERPLEXITY_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="perplexity",
    adapter_id="perplexity-search",
    domain="web",
    adapter_reason="existing WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=ClientTransportDeclaration(
        host="api.perplexity.ai",
        protocol="json",
        operations=(HttpOperation(method="POST", endpoint="/chat/completions"),),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="PERPLEXITY_API_KEY",
        field_name="Authorization",
        required=True,
    ),
    configuration_keys=("enabled",),
)
