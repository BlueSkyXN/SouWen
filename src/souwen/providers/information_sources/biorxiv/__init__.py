"""Built-in bioRxiv Provider v2 package."""

from .adapter import BioRxivClientProtocol, BioRxivSearchProvider
from .manifest import BIORXIV_PROVIDER_MANIFEST
from .spec import BIORXIV_PROVIDER_SPEC

__all__ = [
    "BIORXIV_PROVIDER_MANIFEST",
    "BIORXIV_PROVIDER_SPEC",
    "BioRxivClientProtocol",
    "BioRxivSearchProvider",
]
