"""Per-source registration declaration (SPEC 7 单模块源形态).

一个源的全部注册信息在此声明：manifest、spec、Provider 类与 provider 构造。
``server.v2_runtime`` 通过目录发现读取本文件，不再为任何源 id 写分支。
"""

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
