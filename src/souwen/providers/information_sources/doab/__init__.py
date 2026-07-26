"""Built-in DOAB Provider v2 package."""

from .adapter import DOABClientProtocol, DOABSearchProvider
from .manifest import DOAB_PROVIDER_MANIFEST
from .spec import DOAB_PROVIDER_SPEC

__all__ = [
    "DOAB_PROVIDER_MANIFEST",
    "DOAB_PROVIDER_SPEC",
    "DOABClientProtocol",
    "DOABSearchProvider",
]
