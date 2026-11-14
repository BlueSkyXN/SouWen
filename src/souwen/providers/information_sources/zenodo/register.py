"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.zenodo import ZenodoClient
from .adapter import ZenodoSearchProvider
from .manifest import ZENODO_PROVIDER_MANIFEST
from .spec import ZENODO_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config, reviewed_proxy
    return ZenodoSearchProvider(
        ZenodoClient(access_token=secrets.get("ZENODO_ACCESS_TOKEN")),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = ZENODO_PROVIDER_MANIFEST
SPEC = ZENODO_PROVIDER_SPEC
PROVIDER_TYPE = ZenodoSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
