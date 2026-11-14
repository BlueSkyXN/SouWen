"""Source package: arxiv（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    ARXIV_PROVIDER_MANIFEST,
    ARXIV_PROVIDER_SPEC,
    ArxivClient,
    ArxivSearchProvider,
    ArxivClientProtocol,
    MANIFEST,
    SPEC,
    PROVIDER_TYPE,
    build_provider,
)
