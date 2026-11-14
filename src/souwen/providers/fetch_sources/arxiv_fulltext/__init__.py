"""Source package: arxiv_fulltext（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    ARXIV_FULLTEXT_PROVIDER_MANIFEST,
    ARXIV_FULLTEXT_FETCH_PROFILE,
    _FETCH_SPEC,
    ArxivFulltextClient,
    ArxivFulltextClientProtocol,
    ArxivFulltextFetchProvider,
    build_provider,
)
