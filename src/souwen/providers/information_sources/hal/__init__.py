"""Built-in HAL Provider v2 package."""

from .adapter import HalClientProtocol, HalSearchProvider
from .manifest import HAL_PROVIDER_MANIFEST
from .spec import HAL_PROVIDER_SPEC

__all__ = ["HAL_PROVIDER_MANIFEST", "HAL_PROVIDER_SPEC", "HalClientProtocol", "HalSearchProvider"]
