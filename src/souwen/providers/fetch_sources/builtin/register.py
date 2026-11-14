"""Per-source registration declaration (SPEC 7 单模块源形态).

一个源的全部注册信息在此声明：manifest 与 Provider 构造。
``server.v2_runtime`` 通过目录发现读取本文件，不再为任何源 id 写分支。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig
from souwen.providers.runtime_clients.web.builtin import BuiltinFetcherClient

from .adapter import BuiltinFetchProvider
from .manifest import BUILTIN_FETCH_MANIFEST


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, reviewed_proxy
    return BuiltinFetchProvider(
        BuiltinFetcherClient(respect_robots_txt=config.respect_robots_txt),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = BUILTIN_FETCH_MANIFEST
SPEC = None
PROVIDER_TYPE = BuiltinFetchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
