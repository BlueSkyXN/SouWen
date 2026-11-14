"""Per-source registration declaration (SPEC 7 单模块源形态).

一个源的全部注册信息在此声明：manifest、spec、Provider 类与 provider 构造。
``server.v2_runtime`` 通过目录发现读取本文件，不再为任何源 id 写分支。
"""

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
