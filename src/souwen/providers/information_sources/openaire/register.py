"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.openaire import OpenAireClient
from .adapter import OpenAireSearchProvider
from .manifest import OPENAIRE_PROVIDER_MANIFEST
from .spec import OPENAIRE_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config, reviewed_proxy
    return OpenAireSearchProvider(
        OpenAireClient(api_key=secrets.get("OPENAIRE_API_KEY")),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = OPENAIRE_PROVIDER_MANIFEST
SPEC = OPENAIRE_PROVIDER_SPEC
PROVIDER_TYPE = OpenAireSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
