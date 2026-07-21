"""Book-domain clients and normalized catalog APIs."""

from souwen.book.open_library import OpenLibraryClient
from souwen.book.internet_archive import InternetArchiveClient
from souwen.book.wikisource import WikisourceClient
from souwen.book.library_of_congress import LibraryOfCongressClient

__all__ = [
    "InternetArchiveClient",
    "LibraryOfCongressClient",
    "OpenLibraryClient",
    "WikisourceClient",
]
