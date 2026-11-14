"""Source package: duckduckgo_news（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    DUCKDUCKGO_NEWS_PROVIDER_MANIFEST,
    DUCKDUCKGO_NEWS_PROVIDER_SPEC,
    DuckDuckGoNewsClient,
    DuckDuckGoNewsSearchProvider,
    build_provider,
)
