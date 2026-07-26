"""Built-in Open Library Provider v2 package."""

from .adapter import OpenLibraryClientProtocol, OpenLibrarySearchProvider
from .manifest import OPEN_LIBRARY_PROVIDER_MANIFEST
from .spec import OPEN_LIBRARY_PROVIDER_SPEC

__all__ = [
    "OPEN_LIBRARY_PROVIDER_MANIFEST",
    "OPEN_LIBRARY_PROVIDER_SPEC",
    "OpenLibraryClientProtocol",
    "OpenLibrarySearchProvider",
]
