"""Built-in Figshare Provider v2 package."""

from .adapter import FigshareClientProtocol, FigshareSearchProvider
from .manifest import FIGSHARE_PROVIDER_MANIFEST
from .spec import FIGSHARE_PROVIDER_SPEC

__all__ = [
    "FIGSHARE_PROVIDER_MANIFEST",
    "FIGSHARE_PROVIDER_SPEC",
    "FigshareClientProtocol",
    "FigshareSearchProvider",
]
