"""Built-in DOAJ Provider v2 package."""

from .adapter import DoajClientProtocol, DoajSearchProvider
from .manifest import DOAJ_PROVIDER_MANIFEST
from .spec import DOAJ_PROVIDER_SPEC

__all__ = [
    "DOAJ_PROVIDER_MANIFEST",
    "DOAJ_PROVIDER_SPEC",
    "DoajClientProtocol",
    "DoajSearchProvider",
]
