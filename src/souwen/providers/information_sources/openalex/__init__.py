"""OpenAlex Provider v2 adapter. Owner: Providers. Allowed dependencies: SPI and common runtime."""

from .adapter import OpenAlexClientProtocol, OpenAlexSearchProvider
from .manifest import OPENALEX_PROVIDER_MANIFEST
from .spec import OPENALEX_REST_SPEC

__all__ = [
    "OPENALEX_PROVIDER_MANIFEST",
    "OPENALEX_REST_SPEC",
    "OpenAlexClientProtocol",
    "OpenAlexSearchProvider",
]
