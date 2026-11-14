"""Source package: hal（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    HAL_PROVIDER_MANIFEST,
    HAL_PROVIDER_SPEC,
    _SPEC,
    HalClient,
    HalClientProtocol,
    HalSearchProvider,
    build_provider,
)
