"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.web.ddg_news import DuckDuckGoNewsClient
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from .adapter import DuckDuckGoNewsSearchProvider
from .manifest import DUCKDUCKGO_NEWS_PROVIDER_MANIFEST
from .spec import DUCKDUCKGO_NEWS_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = DuckDuckGoNewsClient()
    return DuckDuckGoNewsSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = DUCKDUCKGO_NEWS_PROVIDER_MANIFEST
SPEC = DUCKDUCKGO_NEWS_PROVIDER_SPEC
PROVIDER_TYPE = DuckDuckGoNewsSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
