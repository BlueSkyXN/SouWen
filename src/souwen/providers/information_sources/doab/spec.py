"""Reviewed search bridge declaration for DOAB."""

from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

DOAB_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="doab",
    adapter_id="doab-search",
    domain="book",
    adapter_reason="bounded OAI-PMH harvest filtering remains in the existing client",
    transport=ClientTransportDeclaration(
        host="directory.doabooks.org",
        protocol="xml",
        operations=(HttpOperation(method="GET", endpoint="/oai/request"),),
    ),
    configuration_keys=("enabled",),
)
__all__ = ["DOAB_PROVIDER_SPEC"]
