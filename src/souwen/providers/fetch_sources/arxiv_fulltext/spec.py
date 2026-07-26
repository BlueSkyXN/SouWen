"""Reviewed static profile for arXiv's source-specific full-text Fetch adapter."""

from souwen.platform.provider_spec import LegacyFetchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


ARXIV_FULLTEXT_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="arxiv_fulltext",
    adapter_id="arxiv_fulltext-fetch",
    bridge_reason="arXiv identifier extraction and HTML text parsing remain in the legacy Fetch bridge",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="arxiv.org",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/html/"),),
    ),
    target_contract="arxiv_publication_url",
    configuration_keys=("enabled",),
)

__all__ = ["ARXIV_FULLTEXT_FETCH_PROFILE"]
