"""Built-in Semantic Scholar Provider v2 package."""

from .adapter import SemanticScholarClientProtocol, SemanticScholarSearchProvider
from .manifest import SEMANTIC_SCHOLAR_PROVIDER_MANIFEST
from .spec import SEMANTIC_SCHOLAR_PROVIDER_SPEC

__all__ = [
    "SEMANTIC_SCHOLAR_PROVIDER_MANIFEST",
    "SEMANTIC_SCHOLAR_PROVIDER_SPEC",
    "SemanticScholarClientProtocol",
    "SemanticScholarSearchProvider",
]
