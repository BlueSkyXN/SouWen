"""Reviewed bridge declaration for perplexity legacy Search."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

PERPLEXITY_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="perplexity",
    adapter_id="perplexity-search",
    domain="web",
    bridge_reason="legacy WebSearchResponse normalization and canonical URL identity require a bridge",
    transport=LegacyTransportDeclaration(
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
