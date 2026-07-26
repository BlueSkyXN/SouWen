"""Built-in LibriVox Provider v2 package."""

from .adapter import LibriVoxClientProtocol, LibriVoxSearchProvider
from .manifest import LIBRIVOX_PROVIDER_MANIFEST
from .spec import LIBRIVOX_PROVIDER_SPEC

__all__ = [
    "LIBRIVOX_PROVIDER_MANIFEST",
    "LIBRIVOX_PROVIDER_SPEC",
    "LibriVoxClientProtocol",
    "LibriVoxSearchProvider",
]
