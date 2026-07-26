"""Built-in OAPEN Provider v2 package."""

from .adapter import OAPENClientProtocol, OAPENSearchProvider
from .manifest import OAPEN_PROVIDER_MANIFEST
from .spec import OAPEN_PROVIDER_SPEC

__all__ = [
    "OAPEN_PROVIDER_MANIFEST",
    "OAPEN_PROVIDER_SPEC",
    "OAPENClientProtocol",
    "OAPENSearchProvider",
]
