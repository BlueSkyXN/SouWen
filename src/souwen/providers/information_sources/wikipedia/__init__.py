"""Built-in wikipedia Provider v2 package."""

from .adapter import WikipediaClientProtocol, WikipediaSearchProvider
from .manifest import WIKIPEDIA_PROVIDER_MANIFEST
from .spec import WIKIPEDIA_PROVIDER_SPEC

__all__ = [
    "WIKIPEDIA_PROVIDER_MANIFEST",
    "WIKIPEDIA_PROVIDER_SPEC",
    "WikipediaClientProtocol",
    "WikipediaSearchProvider",
]
