"""Built-in Project Gutenberg local-catalog Provider v2 package."""

from .adapter import GutenbergClientProtocol, GutenbergSearchProvider
from .manifest import GUTENBERG_PROVIDER_MANIFEST
from .spec import GUTENBERG_PROVIDER_SPEC

__all__ = [
    "GUTENBERG_PROVIDER_MANIFEST",
    "GUTENBERG_PROVIDER_SPEC",
    "GutenbergClientProtocol",
    "GutenbergSearchProvider",
]
