"""Built-in linkup Provider v2 package."""

from .adapter import LinkupClientProtocol, LinkupSearchProvider
from .manifest import LINKUP_PROVIDER_MANIFEST
from .spec import LINKUP_PROVIDER_SPEC

__all__ = [
    "LINKUP_PROVIDER_MANIFEST",
    "LINKUP_PROVIDER_SPEC",
    "LinkupClientProtocol",
    "LinkupSearchProvider",
]
