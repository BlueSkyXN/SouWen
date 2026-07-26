"""Built-in Wikisource Provider v2 package."""

from .adapter import WikisourceClientProtocol, WikisourceSearchProvider
from .manifest import WIKISOURCE_PROVIDER_MANIFEST
from .spec import WIKISOURCE_PROVIDER_SPEC

__all__ = [
    "WIKISOURCE_PROVIDER_MANIFEST",
    "WIKISOURCE_PROVIDER_SPEC",
    "WikisourceClientProtocol",
    "WikisourceSearchProvider",
]
