"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.iacr import IacrClient
from .adapter import IacrSearchProvider
from .manifest import IACR_PROVIDER_MANIFEST
from .spec import IACR_BRIDGE_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return IacrSearchProvider(
        IacrClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = IACR_PROVIDER_MANIFEST
SPEC = IACR_BRIDGE_SPEC
PROVIDER_TYPE = IacrSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
