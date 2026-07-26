"""Built-in CORE Provider v2 package."""

from .adapter import CoreClientProtocol, CoreSearchProvider
from .manifest import CORE_PROVIDER_MANIFEST
from .spec import CORE_PROVIDER_SPEC

__all__ = [
    "CORE_PROVIDER_MANIFEST",
    "CORE_PROVIDER_SPEC",
    "CoreClientProtocol",
    "CoreSearchProvider",
]
