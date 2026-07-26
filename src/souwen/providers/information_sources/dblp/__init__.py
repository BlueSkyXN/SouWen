"""Built-in DBLP Provider v2 package."""

from .adapter import DblpClientProtocol, DblpSearchProvider
from .manifest import DBLP_PROVIDER_MANIFEST
from .spec import DBLP_PROVIDER_SPEC

__all__ = [
    "DBLP_PROVIDER_MANIFEST",
    "DBLP_PROVIDER_SPEC",
    "DblpClientProtocol",
    "DblpSearchProvider",
]
