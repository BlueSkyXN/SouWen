"""Built-in serpapi Provider v2 package."""

from .adapter import SerpApiClientProtocol, SerpApiSearchProvider
from .manifest import SERPAPI_PROVIDER_MANIFEST
from .spec import SERPAPI_PROVIDER_SPEC

__all__ = [
    "SERPAPI_PROVIDER_MANIFEST",
    "SERPAPI_PROVIDER_SPEC",
    "SerpApiClientProtocol",
    "SerpApiSearchProvider",
]
