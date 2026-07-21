"""Book-domain clients and normalized catalog APIs."""

from souwen.book.open_library import OpenLibraryClient
from souwen.book.internet_archive import InternetArchiveClient

__all__ = ["InternetArchiveClient", "OpenLibraryClient"]
