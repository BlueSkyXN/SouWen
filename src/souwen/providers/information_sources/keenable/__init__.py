"""Built-in keenable Provider v2 package."""

from .adapter import KeenableClientProtocol, KeenableSearchProvider
from .manifest import KEENABLE_PROVIDER_MANIFEST
from .spec import KEENABLE_PROVIDER_SPEC

__all__ = [
    "KEENABLE_PROVIDER_MANIFEST",
    "KEENABLE_PROVIDER_SPEC",
    "KeenableClientProtocol",
    "KeenableSearchProvider",
]
