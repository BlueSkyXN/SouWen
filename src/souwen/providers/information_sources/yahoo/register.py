"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig
from souwen.providers.runtime_clients.web.yahoo import YahooClient

from .adapter import YahooSearchProvider
from .manifest import YAHOO_PROVIDER_MANIFEST
from .spec import YAHOO_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets
    from souwen.common_runtime.channel_overrides import without_source_channel_overrides
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = YahooClient(follow_redirects=False)
    return YahooSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


# v2_runtime 的统一注册循环消费这三个字段 + build_provider。
MANIFEST = YAHOO_PROVIDER_MANIFEST
SPEC = YAHOO_PROVIDER_SPEC
PROVIDER_TYPE = YahooSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
