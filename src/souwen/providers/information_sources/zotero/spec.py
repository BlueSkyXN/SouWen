"""Reviewed bridge declaration for a configured Zotero library."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

ZOTERO_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="zotero",
    adapter_id="zotero-search",
    adapter_reason="library-scoped paths and item-key identity require a bridge",
    transport=ClientTransportDeclaration(
        host="api.zotero.org",
        base_path="/",
        protocol="json",
        operations=(
            HttpOperation(method="GET", endpoint="/users/"),
            HttpOperation(method="GET", endpoint="/groups/"),
        ),
    ),
    auth=AuthDeclaration(
        placement="header", reference="ZOTERO_API_KEY", field_name="Zotero-API-Key"
    ),
    configuration_keys=("enabled", "library_id", "library_type"),
)
