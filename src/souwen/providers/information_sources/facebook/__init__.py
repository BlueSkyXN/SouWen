"""Built-in facebook Provider v2 package."""

from .adapter import FacebookClientProtocol, FacebookSearchProvider
from .manifest import FACEBOOK_PROVIDER_MANIFEST
from .spec import FACEBOOK_PROVIDER_SPEC

__all__ = [
    "FACEBOOK_PROVIDER_MANIFEST",
    "FACEBOOK_PROVIDER_SPEC",
    "FacebookClientProtocol",
    "FacebookSearchProvider",
]
