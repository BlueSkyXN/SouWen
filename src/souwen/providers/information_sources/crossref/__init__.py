"""Source package: crossref（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    CROSSREF_PROVIDER_MANIFEST,
    CROSSREF_PROVIDER_SPEC,
    _SPEC,
    CrossrefClient,
    CrossrefClientProtocol,
    CrossrefSearchProvider,
    build_provider,
)
