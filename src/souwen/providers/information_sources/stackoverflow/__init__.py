"""Built-in stackoverflow Provider v2 package."""

from .adapter import StackOverflowClientProtocol, StackOverflowSearchProvider
from .manifest import STACKOVERFLOW_PROVIDER_MANIFEST
from .spec import STACKOVERFLOW_PROVIDER_SPEC

__all__ = [
    "STACKOVERFLOW_PROVIDER_MANIFEST",
    "STACKOVERFLOW_PROVIDER_SPEC",
    "StackOverflowClientProtocol",
    "StackOverflowSearchProvider",
]
