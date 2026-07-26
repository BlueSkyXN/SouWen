"""Built-in PatentsView Provider v2 package."""

from .adapter import PatentsViewClientProtocol, PatentsViewSearchProvider
from .manifest import PATENTSVIEW_PROVIDER_MANIFEST
from .spec import PATENTSVIEW_REST_SPEC

__all__ = [
    "PATENTSVIEW_PROVIDER_MANIFEST",
    "PATENTSVIEW_REST_SPEC",
    "PatentsViewClientProtocol",
    "PatentsViewSearchProvider",
]
