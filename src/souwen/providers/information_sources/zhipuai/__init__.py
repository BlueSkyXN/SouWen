"""Built-in zhipuai Provider v2 package."""

from .adapter import ZhipuAISearchClientProtocol, ZhipuAISearchSearchProvider
from .manifest import ZHIPUAI_PROVIDER_MANIFEST
from .spec import ZHIPUAI_PROVIDER_SPEC

__all__ = [
    "ZHIPUAI_PROVIDER_MANIFEST",
    "ZHIPUAI_PROVIDER_SPEC",
    "ZhipuAISearchClientProtocol",
    "ZhipuAISearchSearchProvider",
]
