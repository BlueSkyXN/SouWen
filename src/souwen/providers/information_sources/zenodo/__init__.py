"""Built-in Zenodo Provider v2 package."""

from .adapter import ZenodoClientProtocol, ZenodoSearchProvider
from .manifest import ZENODO_PROVIDER_MANIFEST
from .spec import ZENODO_PROVIDER_SPEC

__all__ = [
    "ZENODO_PROVIDER_MANIFEST",
    "ZENODO_PROVIDER_SPEC",
    "ZenodoClientProtocol",
    "ZenodoSearchProvider",
]
