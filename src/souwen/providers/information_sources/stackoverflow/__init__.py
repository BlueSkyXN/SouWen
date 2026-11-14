"""Source package: stackoverflow（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    STACKOVERFLOW_PROVIDER_MANIFEST,
    STACKOVERFLOW_PROVIDER_SPEC,
    _SPEC,
    StackOverflowClient,
    StackOverflowClientProtocol,
    StackOverflowSearchProvider,
    build_provider,
)
