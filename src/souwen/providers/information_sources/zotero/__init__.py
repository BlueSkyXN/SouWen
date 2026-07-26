"""Built-in Zotero Provider v2 package."""

from .adapter import ZoteroClientProtocol, ZoteroSearchProvider
from .manifest import ZOTERO_PROVIDER_MANIFEST
from .spec import ZOTERO_PROVIDER_SPEC

__all__ = [
    "ZOTERO_PROVIDER_MANIFEST",
    "ZOTERO_PROVIDER_SPEC",
    "ZoteroClientProtocol",
    "ZoteroSearchProvider",
]
