"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig
from souwen.providers.runtime_clients.paper.arxiv import ArxivClient

from .adapter import ArxivSearchProvider
from .manifest import ARXIV_PROVIDER_MANIFEST
from .spec import ARXIV_PROVIDER_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无代理通道
    return ArxivSearchProvider(ArxivClient(), enabled=bool(configuration["enabled"]))


MANIFEST = ARXIV_PROVIDER_MANIFEST
SPEC = ARXIV_PROVIDER_SPEC
PROVIDER_TYPE = ArxivSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
