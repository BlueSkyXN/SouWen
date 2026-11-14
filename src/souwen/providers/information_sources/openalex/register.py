"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig
from souwen.providers.runtime_clients.paper.openalex import OpenAlexClient

from .adapter import OpenAlexSearchProvider
from .manifest import OPENALEX_PROVIDER_MANIFEST
from .spec import OPENALEX_REST_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del configuration, secrets, reviewed_proxy
    return OpenAlexSearchProvider(
        OpenAlexClient(api_key=config.resolve_api_key("openalex", "openalex_api_key")),
        enabled=True,
    )


def resolve_configuration(config: SouWenConfig) -> dict[str, object]:
    if not config.is_source_enabled("openalex", default=True):
        raise ValueError("provider is disabled")
    return {"enabled": True}


MANIFEST = OPENALEX_PROVIDER_MANIFEST
SPEC = OPENALEX_REST_SPEC
PROVIDER_TYPE = OpenAlexSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider", "resolve_configuration"]
