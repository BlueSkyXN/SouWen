"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.web.wayback import WaybackClient

from .adapter import WaybackFetchProvider
from .manifest import WAYBACK_PROVIDER_MANIFEST
from .spec import WAYBACK_FETCH_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config
    from souwen.common_runtime.channel_overrides import without_source_channel_overrides

    # 未声明的频道覆盖不生效：wayback 不支持代理/自定义 base_url，构造期
    # 以受审空覆盖运行（与旧 _build_reviewed_client_provider 语义一致）。
    with without_source_channel_overrides(proxy=None):
        client = WaybackClient()
    return WaybackFetchProvider(client, enabled=bool(configuration["enabled"]))


MANIFEST = WAYBACK_PROVIDER_MANIFEST
SPEC = WAYBACK_FETCH_PROVIDER_SPEC
PROVIDER_TYPE = WaybackFetchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
