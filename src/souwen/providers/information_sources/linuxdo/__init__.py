"""Built-in linuxdo Provider v2 package."""

from .adapter import LinuxDoClientProtocol, LinuxDoSearchProvider
from .manifest import LINUXDO_PROVIDER_MANIFEST
from .spec import LINUXDO_PROVIDER_SPEC

__all__ = [
    "LINUXDO_PROVIDER_MANIFEST",
    "LINUXDO_PROVIDER_SPEC",
    "LinuxDoClientProtocol",
    "LinuxDoSearchProvider",
]
