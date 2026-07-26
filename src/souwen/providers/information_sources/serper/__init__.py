"""Built-in serper Provider v2 package."""

from .adapter import SerperClientProtocol, SerperSearchProvider
from .manifest import SERPER_PROVIDER_MANIFEST
from .spec import SERPER_PROVIDER_SPEC

__all__ = [
    "SERPER_PROVIDER_MANIFEST",
    "SERPER_PROVIDER_SPEC",
    "SerperClientProtocol",
    "SerperSearchProvider",
]
