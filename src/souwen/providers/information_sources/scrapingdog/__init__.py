"""Built-in scrapingdog Provider v2 package."""

from .adapter import ScrapingDogClientProtocol, ScrapingDogSearchProvider
from .manifest import SCRAPINGDOG_PROVIDER_MANIFEST
from .spec import SCRAPINGDOG_PROVIDER_SPEC

__all__ = [
    "SCRAPINGDOG_PROVIDER_MANIFEST",
    "SCRAPINGDOG_PROVIDER_SPEC",
    "ScrapingDogClientProtocol",
    "ScrapingDogSearchProvider",
]
