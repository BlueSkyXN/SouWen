"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.patent.uspto_odp import UsptoOdpClient
from .adapter import UsptoOdpSearchProvider
from .manifest import USPTO_ODP_PROVIDER_MANIFEST
from .spec import USPTO_ODP_BRIDGE_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config, reviewed_proxy
    return UsptoOdpSearchProvider(
        UsptoOdpClient(api_key=secrets["USPTO_API_KEY"]),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = USPTO_ODP_PROVIDER_MANIFEST
SPEC = USPTO_ODP_BRIDGE_SPEC
PROVIDER_TYPE = UsptoOdpSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
