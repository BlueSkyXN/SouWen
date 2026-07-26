"""Built-in HuggingFace Papers Provider v2 package."""

from .adapter import HuggingFaceClientProtocol, HuggingFaceSearchProvider
from .manifest import HUGGINGFACE_PROVIDER_MANIFEST
from .spec import HUGGINGFACE_REST_SPEC

__all__ = [
    "HUGGINGFACE_PROVIDER_MANIFEST",
    "HUGGINGFACE_REST_SPEC",
    "HuggingFaceClientProtocol",
    "HuggingFaceSearchProvider",
]
