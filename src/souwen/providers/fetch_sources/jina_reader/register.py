"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.web.jina_reader import JinaReaderClient

from .adapter import JinaReaderFetchProvider
from .manifest import JINA_READER_PROVIDER_MANIFEST
from .spec import JINA_READER_FETCH_PROFILE


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config
    from souwen.common_runtime.channel_overrides import without_source_channel_overrides

    with without_source_channel_overrides(proxy=reviewed_proxy):
        client = JinaReaderClient(api_key=secrets.get("JINA_API_KEY"))
    return JinaReaderFetchProvider(client, enabled=bool(configuration["enabled"]))


MANIFEST = JINA_READER_PROVIDER_MANIFEST
SPEC = JINA_READER_FETCH_PROFILE
PROVIDER_TYPE = JinaReaderFetchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
