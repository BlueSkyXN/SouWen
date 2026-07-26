"""Built-in Library of Congress Provider v2 package."""

from .adapter import LibraryOfCongressClientProtocol, LibraryOfCongressSearchProvider
from .manifest import LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST
from .spec import LIBRARY_OF_CONGRESS_PROVIDER_SPEC

__all__ = [
    "LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST",
    "LIBRARY_OF_CONGRESS_PROVIDER_SPEC",
    "LibraryOfCongressClientProtocol",
    "LibraryOfCongressSearchProvider",
]
