"""Per-source registration declaration (SPEC 7 单模块源形态).

一个源的全部注册信息在此声明：manifest、spec、Provider 类与 provider 构造。
``server.v2_runtime`` 通过目录发现读取本文件，不再为任何源 id 写分支。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.providers.runtime_clients.web.searxng import SearXNGClient

from .adapter import SearXNGSearchProvider
from .manifest import SEARXNG_PROVIDER_MANIFEST
from .spec import SEARXNG_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    source_timeout = config.get_source_config("searxng").timeout or config.timeout
    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=source_timeout,
        max_retries=config.max_retries,
    ):
        client = SearXNGClient(instance_url=str(configuration["base_url"]), follow_redirects=False)
    return SearXNGSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


def resolve_configuration(config: SouWenConfig) -> dict[str, object]:
    if not config.is_source_enabled("searxng", default=True):
        raise ValueError("provider is disabled")
    from souwen.platform.provider_spec import validate_self_hosted_base_url

    value = config.resolve_base_url("searxng", getattr(config, "searxng_url", None) or "")
    return {"enabled": True, "base_url": validate_self_hosted_base_url(value)}


MANIFEST = SEARXNG_PROVIDER_MANIFEST
SPEC = SEARXNG_PROVIDER_SPEC
PROVIDER_TYPE = SearXNGSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider", "resolve_configuration"]
