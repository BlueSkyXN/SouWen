"""Per-source registration declaration (SPEC 7 单模块源形态).

一个源的全部注册信息在此声明：manifest、spec（若有）、Provider 类与 provider
构造。``server.v2_runtime`` 通过目录发现读取本文件，不再为任何源 id 写分支。
"""

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
