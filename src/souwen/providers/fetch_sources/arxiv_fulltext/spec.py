"""Reviewed static profile for arXiv's source-specific full-text Fetch adapter."""

from souwen.platform.provider_spec import ClientFetchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation


ARXIV_FULLTEXT_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="arxiv_fulltext",
    adapter_id="arxiv_fulltext-fetch",
    adapter_reason="arXiv identifier extraction and HTML text parsing remain in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="arxiv.org",
        protocol="html",
        operations=(HttpOperation(method="GET", endpoint="/html/"),),
    ),
    target_contract="arxiv_publication_url",
    configuration_keys=("enabled",),
)

__all__ = ["ARXIV_FULLTEXT_FETCH_PROFILE"]
