"""Source package: jina_reader（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    JINA_READER_PROVIDER_MANIFEST,
    JINA_READER_FETCH_PROFILE,
    _FETCH_SPEC,
    JinaReaderClient,
    JinaReaderClientProtocol,
    JinaReaderFetchProvider,
    build_provider,
)
