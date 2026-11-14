"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.patent.epo_ops import EpoOpsClient
from .adapter import EpoOpsSearchProvider
from .manifest import EPO_OPS_PROVIDER_MANIFEST
from .spec import EPO_OPS_BRIDGE_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config, reviewed_proxy
    return EpoOpsSearchProvider(
        EpoOpsClient(
            consumer_key=secrets["EPO_CONSUMER_KEY"], consumer_secret=secrets["EPO_CONSUMER_SECRET"]
        ),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = EPO_OPS_PROVIDER_MANIFEST
SPEC = EPO_OPS_BRIDGE_SPEC
PROVIDER_TYPE = EpoOpsSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
