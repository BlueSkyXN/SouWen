"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.doaj import DoajClient
from .adapter import DoajSearchProvider
from .manifest import DOAJ_PROVIDER_MANIFEST
from .spec import DOAJ_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config, reviewed_proxy
    return DoajSearchProvider(
        DoajClient(api_key=secrets.get("DOAJ_API_KEY")),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = DOAJ_PROVIDER_MANIFEST
SPEC = DOAJ_PROVIDER_SPEC
PROVIDER_TYPE = DoajSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
