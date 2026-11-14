"""Source package: searxng（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    SEARXNG_PROVIDER_MANIFEST,
    SEARXNG_PROVIDER_SPEC,
    SearXNGClient,
    SearXNGSearchProvider,
    build_provider,
    resolve_configuration,
)
