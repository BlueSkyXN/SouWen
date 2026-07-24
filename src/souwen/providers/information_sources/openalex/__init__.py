"""OpenAlex Provider v2 adapter. Owner: Providers. Allowed dependencies: SPI and common runtime."""

from .adapter import OpenAlexClientProtocol, OpenAlexSearchProvider
from .manifest import OPENALEX_PROVIDER_MANIFEST

__all__ = ["OPENALEX_PROVIDER_MANIFEST", "OpenAlexClientProtocol", "OpenAlexSearchProvider"]
