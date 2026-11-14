"""Per-source registration declaration (SPEC 7 单模块源形态).

一个源的全部注册信息在此声明：manifest、spec、Provider 类与 provider 构造。
``server.v2_runtime`` 通过目录发现读取本文件，不再为任何源 id 写分支。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.book.library_of_congress import LibraryOfCongressClient
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from .adapter import LibraryOfCongressSearchProvider
from .manifest import LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST
from .spec import LIBRARY_OF_CONGRESS_PROVIDER_SPEC


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
        client = LibraryOfCongressClient()
    return LibraryOfCongressSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST
SPEC = LIBRARY_OF_CONGRESS_PROVIDER_SPEC
PROVIDER_TYPE = LibraryOfCongressSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
