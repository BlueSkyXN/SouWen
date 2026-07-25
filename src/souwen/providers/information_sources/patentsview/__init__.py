"""Built-in PatentsView Provider v2 package."""

from .adapter import PatentsViewClientProtocol, PatentsViewSearchProvider
from .manifest import PATENTSVIEW_PROVIDER_MANIFEST

__all__ = [
    "PATENTSVIEW_PROVIDER_MANIFEST",
    "PatentsViewClientProtocol",
    "PatentsViewSearchProvider",
]
