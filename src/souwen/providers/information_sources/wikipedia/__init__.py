"""Source package: wikipedia（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    WIKIPEDIA_PROVIDER_MANIFEST,
    WIKIPEDIA_PROVIDER_SPEC,
    _SPEC,
    WikipediaClient,
    WikipediaClientProtocol,
    WikipediaSearchProvider,
    build_provider,
)
