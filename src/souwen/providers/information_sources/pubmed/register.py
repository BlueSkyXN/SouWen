"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.pubmed import PubMedClient
from .adapter import PubMedSearchProvider
from .manifest import PUBMED_PROVIDER_MANIFEST
from .spec import PUBMED_BRIDGE_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config, reviewed_proxy
    return PubMedSearchProvider(
        PubMedClient(api_key=secrets.get("PUBMED_API_KEY")),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = PUBMED_PROVIDER_MANIFEST
SPEC = PUBMED_BRIDGE_SPEC
PROVIDER_TYPE = PubMedSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
