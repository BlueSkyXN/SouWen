"""Built-in IEEE Xplore Provider v2 package."""

from .adapter import IeeeXploreClientProtocol, IeeeXploreSearchProvider
from .manifest import IEEE_XPLORE_PROVIDER_MANIFEST
from .spec import IEEE_XPLORE_PROVIDER_SPEC

__all__ = [
    "IEEE_XPLORE_PROVIDER_MANIFEST",
    "IEEE_XPLORE_PROVIDER_SPEC",
    "IeeeXploreClientProtocol",
    "IeeeXploreSearchProvider",
]
