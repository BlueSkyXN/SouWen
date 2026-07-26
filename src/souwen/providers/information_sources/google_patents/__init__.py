"""Google Patents Provider v2 bridge package."""

from .adapter import GooglePatentsClientProtocol, GooglePatentsSearchProvider
from .manifest import GOOGLE_PATENTS_PROVIDER_MANIFEST
from .spec import GOOGLE_PATENTS_BRIDGE_SPEC

__all__ = [
    "GOOGLE_PATENTS_BRIDGE_SPEC",
    "GOOGLE_PATENTS_PROVIDER_MANIFEST",
    "GooglePatentsClientProtocol",
    "GooglePatentsSearchProvider",
]
