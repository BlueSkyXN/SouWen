"""Typed, static Provider v2 specifications and generic adapter helpers."""

from .factory import (
    ClientFetchProvider,
    ClientFetchSpec,
    ClientSearchProvider,
    ClientSearchSpec,
    RestJsonSearchProvider,
)
from .cn_scraper import CnScraperBinding, CnScraperSearchProvider, cn_scraper_search_spec
from .search_scraper import (
    ScraperSearchProvider,
    canonical_public_url,
    client_scraper_spec,
    scraper_search_manifest,
)
from .models import (
    AuthDeclaration,
    CredentialBinding,
    HttpOperation,
    ClientFetchProviderSpec,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
    LocalStoreDeclaration,
    ProviderSpec,
    PublicTargetDeclaration,
    RestJsonProviderSpec,
    SelfHostedTransportDeclaration,
)
from .self_hosted import validate_self_hosted_base_url
from .resolver import resolve_provider_inputs
from .validation import validate_spec_manifest

__all__ = [
    "AuthDeclaration",
    "CredentialBinding",
    "HttpOperation",
    "CnScraperBinding",
    "CnScraperSearchProvider",
    "ClientFetchProvider",
    "ClientFetchProviderSpec",
    "ClientFetchSpec",
    "ClientSearchProvider",
    "ClientSearchProviderSpec",
    "ClientSearchSpec",
    "ClientTransportDeclaration",
    "LocalStoreDeclaration",
    "ProviderSpec",
    "PublicTargetDeclaration",
    "RestJsonProviderSpec",
    "RestJsonSearchProvider",
    "ScraperSearchProvider",
    "SelfHostedTransportDeclaration",
    "canonical_public_url",
    "client_scraper_spec",
    "scraper_search_manifest",
    "resolve_provider_inputs",
    "validate_spec_manifest",
    "validate_self_hosted_base_url",
    "cn_scraper_search_spec",
]
