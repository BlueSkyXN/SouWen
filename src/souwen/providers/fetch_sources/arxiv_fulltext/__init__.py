"""arXiv full-text Provider v2 Fetch bridge package."""

from .adapter import ArxivFulltextClientProtocol, ArxivFulltextFetchProvider
from .manifest import ARXIV_FULLTEXT_PROVIDER_MANIFEST
from .spec import ARXIV_FULLTEXT_FETCH_PROFILE

__all__ = [
    "ARXIV_FULLTEXT_FETCH_PROFILE",
    "ARXIV_FULLTEXT_PROVIDER_MANIFEST",
    "ArxivFulltextClientProtocol",
    "ArxivFulltextFetchProvider",
]
