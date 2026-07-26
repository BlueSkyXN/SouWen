"""Reviewed bridge declaration for IEEE Xplore search."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

IEEE_XPLORE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="ieee_xplore",
    adapter_id="ieee-xplore-search",
    adapter_reason="article-number identity and IEEE record URL fallback require a bridge",
    transport=ClientTransportDeclaration(
        host="ieeexploreapi.ieee.org",
        base_path="/api/v1",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/articles"),),
    ),
    auth=AuthDeclaration(placement="query", reference="IEEE_API_KEY", field_name="apikey"),
    configuration_keys=("enabled",),
)
