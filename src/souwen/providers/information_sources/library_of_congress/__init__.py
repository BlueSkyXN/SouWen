"""Source package: library_of_congress（全部定义见 source.py，此处转发历史导入路径）。"""

from .source import (  # noqa: F401 — 兼容既有导入路径
    LIBRARY_OF_CONGRESS_PROVIDER_MANIFEST,
    LIBRARY_OF_CONGRESS_PROVIDER_SPEC,
    LibraryOfCongressClient,
    LibraryOfCongressClientProtocol,
    LibraryOfCongressSearchProvider,
    build_provider,
)
