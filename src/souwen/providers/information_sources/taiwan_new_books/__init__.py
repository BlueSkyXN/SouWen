"""Built-in Taiwan new-books local-catalog Provider v2 package."""

from .adapter import TaiwanNewBooksClientProtocol, TaiwanNewBooksSearchProvider
from .manifest import TAIWAN_NEW_BOOKS_PROVIDER_MANIFEST
from .spec import TAIWAN_NEW_BOOKS_PROVIDER_SPEC

__all__ = [
    "TAIWAN_NEW_BOOKS_PROVIDER_MANIFEST",
    "TAIWAN_NEW_BOOKS_PROVIDER_SPEC",
    "TaiwanNewBooksClientProtocol",
    "TaiwanNewBooksSearchProvider",
]
