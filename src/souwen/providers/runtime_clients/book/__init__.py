"""历史导入路径转发：各源 client 已并入 information_sources/fetch_sources 的 source.py。"""

from __future__ import annotations

from souwen.providers.information_sources.internet_archive.source import InternetArchiveClient  # noqa: F401
from souwen.providers.information_sources.library_of_congress.source import LibraryOfCongressClient  # noqa: F401
from souwen.providers.information_sources.open_library.source import OpenLibraryClient  # noqa: F401

__all__ = [
    "InternetArchiveClient",
    "LibraryOfCongressClient",
    "OpenLibraryClient",
]
