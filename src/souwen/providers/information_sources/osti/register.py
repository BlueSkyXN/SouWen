"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.osti import OstiClient
from .adapter import OstiSearchProvider
from .manifest import OSTI_PROVIDER_MANIFEST
from .spec import OSTI_BRIDGE_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return OstiSearchProvider(
        OstiClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = OSTI_PROVIDER_MANIFEST
SPEC = OSTI_BRIDGE_SPEC
PROVIDER_TYPE = OstiSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
