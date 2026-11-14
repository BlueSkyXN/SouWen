"""Source package: open_library（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    OPEN_LIBRARY_PROVIDER_MANIFEST,
    OPEN_LIBRARY_PROVIDER_SPEC,
    OpenLibraryClient,
    OpenLibraryClientProtocol,
    OpenLibrarySearchProvider,
    build_provider,
)
