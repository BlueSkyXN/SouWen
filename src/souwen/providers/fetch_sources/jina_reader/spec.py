"""Reviewed bridge declaration for Jina Reader Fetch."""

from souwen.platform.provider_spec import ClientFetchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

JINA_READER_FETCH_PROFILE = ClientFetchProviderSpec(
    provider_id="jina_reader",
    adapter_id="jina-reader-fetch",
    adapter_reason="Jina Reader path encoding and response variants remain in the existing Fetch bridge",
    transport=ClientTransportDeclaration(
        host="r.jina.ai", protocol="json", operations=(HttpOperation(method="GET", endpoint="/"),)
    ),
    auth=AuthDeclaration(
        placement="bearer", reference="JINA_API_KEY", field_name="Authorization", required=False
    ),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["JINA_READER_FETCH_PROFILE"]
