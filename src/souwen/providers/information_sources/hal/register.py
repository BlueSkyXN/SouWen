"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.hal import HalClient
from .adapter import HalSearchProvider
from .manifest import HAL_PROVIDER_MANIFEST
from .spec import HAL_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return HalSearchProvider(
        HalClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = HAL_PROVIDER_MANIFEST
SPEC = HAL_PROVIDER_SPEC
PROVIDER_TYPE = HalSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
