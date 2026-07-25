"""Built-in ERIC Provider v2 package."""

from .adapter import EricClientProtocol, EricSearchProvider
from .manifest import ERIC_PROVIDER_MANIFEST

__all__ = ["ERIC_PROVIDER_MANIFEST", "EricClientProtocol", "EricSearchProvider"]
