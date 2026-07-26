"""Reviewed bridge declaration for DOAJ article search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

DOAJ_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="doaj",
    adapter_id="doaj-search",
    adapter_reason="encoded query path and article-id canonical URLs require a bridge",
    transport=ClientTransportDeclaration(
        host="doaj.org",
        base_path="/api",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/articles/"),),
    ),
    auth=AuthDeclaration(
        placement="header", reference="DOAJ_API_KEY", field_name="X-API-Key", required=False
    ),
    configuration_keys=("enabled",),
)
