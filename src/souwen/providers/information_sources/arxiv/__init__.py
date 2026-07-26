"""Built-in arXiv Provider v2 package."""

from .adapter import ArxivClientProtocol, ArxivSearchProvider
from .manifest import ARXIV_PROVIDER_MANIFEST
from .spec import ARXIV_PROVIDER_SPEC

__all__ = [
    "ARXIV_PROVIDER_MANIFEST",
    "ARXIV_PROVIDER_SPEC",
    "ArxivClientProtocol",
    "ArxivSearchProvider",
]
