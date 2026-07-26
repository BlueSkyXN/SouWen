"""Built-in Crossref Provider v2 package."""

from .adapter import CrossrefClientProtocol, CrossrefSearchProvider
from .manifest import CROSSREF_PROVIDER_MANIFEST
from .spec import CROSSREF_PROVIDER_SPEC

__all__ = [
    "CROSSREF_PROVIDER_MANIFEST",
    "CROSSREF_PROVIDER_SPEC",
    "CrossrefClientProtocol",
    "CrossrefSearchProvider",
]
