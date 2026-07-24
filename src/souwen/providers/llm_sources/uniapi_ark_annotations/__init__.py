"""Immutable UniAPI Ark annotation Provider v2 adapters."""

from .adapter import (
    UniApiArkAnnotationsDeepSeekProvider,
    UniApiArkAnnotationsDoubaoProvider,
)
from .manifest import (
    UNIAPI_ARK_DEEPSEEK_MANIFEST,
    UNIAPI_ARK_DOUBAO_MANIFEST,
    UNIAPI_ARK_MANIFESTS,
)

__all__ = [
    "UNIAPI_ARK_DEEPSEEK_MANIFEST",
    "UNIAPI_ARK_DOUBAO_MANIFEST",
    "UNIAPI_ARK_MANIFESTS",
    "UniApiArkAnnotationsDeepSeekProvider",
    "UniApiArkAnnotationsDoubaoProvider",
]
