"""Built-in ERIC Provider v2 package."""

from .adapter import EricClientProtocol, EricSearchProvider
from .manifest import ERIC_PROVIDER_MANIFEST
from .spec import ERIC_REST_SPEC

__all__ = [
    "ERIC_PROVIDER_MANIFEST",
    "ERIC_REST_SPEC",
    "EricClientProtocol",
    "EricSearchProvider",
]
