"""PubMed Provider v2 Search bridge package."""

from .adapter import PubMedClientProtocol, PubMedSearchProvider
from .manifest import PUBMED_PROVIDER_MANIFEST
from .spec import PUBMED_BRIDGE_SPEC

__all__ = [
    "PUBMED_BRIDGE_SPEC",
    "PUBMED_PROVIDER_MANIFEST",
    "PubMedClientProtocol",
    "PubMedSearchProvider",
]
