"""Per-source registration (SPEC 7): manifest/spec/provider 与构造，目录发现注册。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from souwen.config import SouWenConfig

from souwen.providers.runtime_clients.paper.huggingface import HuggingFaceClient
from .adapter import HuggingFaceSearchProvider
from .manifest import HUGGINGFACE_PROVIDER_MANIFEST
from .spec import HUGGINGFACE_REST_SPEC


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return HuggingFaceSearchProvider(
        HuggingFaceClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = HUGGINGFACE_PROVIDER_MANIFEST
SPEC = HUGGINGFACE_REST_SPEC
PROVIDER_TYPE = HuggingFaceSearchProvider

__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
