"""Source package: pubmed（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    PUBMED_PROVIDER_MANIFEST,
    PUBMED_BRIDGE_SPEC,
    _BRIDGE_SPEC,
    PubMedClient,
    PubMedClientProtocol,
    PubMedSearchProvider,
    build_provider,
)
